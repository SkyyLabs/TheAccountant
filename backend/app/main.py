import datetime
import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from app import __version__, db
from app.categorize import categorizer
from app.config import REPO_ROOT, Settings
from app.errors import ApiError, error_response, install_error_handlers
from app.llm import get_llm_provider
from app.statements import csv_import, importer, layout, passwords, pdf
from app.statements.csv_import import CsvError, CsvMapping
from app.statements.dates import FORMATS
from app.statements.money import AmountError, parse_amount
from app.statements.pdf import PdfError
from app.statements.reconciliation import find_balance, reconcile

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    # One connection per request: sqlite3 connections must not be shared across the
    # threads FastAPI runs sync endpoints on.
    connection = db.connect(request.app.state.settings.database_path)
    try:
        yield connection
    finally:
        connection.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]


def _amount_filter(name: str, text: str | None) -> int | None:
    if text is None or not text.strip():
        return None
    try:
        # Both currencies use two decimals, so either reads the typed amount the same way.
        return abs(parse_amount(text, "USD"))
    except AmountError:
        raise ApiError(422, "invalid_request", f"{name}: not an amount") from None


def transaction_filters(
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    category_ids: Annotated[list[int], Query()] = [],  # noqa: B006 (FastAPI copies it)
    account_ids: Annotated[list[int], Query()] = [],  # noqa: B006
    currency: Literal["USD", "INR"] | None = None,
    amount_min: str | None = None,
    amount_max: str | None = None,
    q: str | None = None,
    spending_only: bool = False,
) -> db.TransactionFilters:
    """Shared by the transaction list and the summary, so both always agree."""
    return db.TransactionFilters(
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        category_ids=category_ids,
        account_ids=account_ids,
        currency=currency,
        amount_min_minor=_amount_filter("amount_min", amount_min),
        amount_max_minor=_amount_filter("amount_max", amount_max),
        text=q.strip() if q and q.strip() else None,
        spending_only=spending_only,
    )


Filters = Annotated[db.TransactionFilters, Depends(transaction_filters)]

CURRENCY_BY_COUNTRY = {"US": "USD", "IN": "INR"}
DEFAULT_DATE_FORMAT_BY_COUNTRY = {"US": "MM/DD/YYYY", "IN": "DD/MM/YYYY"}


class Bank(BaseModel):
    id: str
    name: str
    country: Literal["US", "IN"]
    currency: Literal["USD", "INR"]
    default_date_format: str
    is_default: bool


class BankCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    country: Literal["US", "IN"]
    default_date_format: str | None = None

    @field_validator("default_date_format")
    @classmethod
    def known_date_format(cls, value: str | None) -> str | None:
        if value is not None and value not in FORMATS:
            raise ValueError(f"must be one of {', '.join(FORMATS)}")
        return value


class Account(BaseModel):
    id: int
    bank_id: str
    bank_name: str
    type: Literal["bank", "credit_card"]
    name: str


class AccountCreate(BaseModel):
    bank_id: str
    type: Literal["bank", "credit_card"]
    name: str = Field(min_length=1, max_length=80)


class Statement(BaseModel):
    id: int
    account_id: int
    bank_id: str
    bank_name: str
    account_name: str
    filename: str
    currency: Literal["USD", "INR"]
    period_start: str | None
    period_end: str | None
    reconciliation_status: Literal["reconciled", "unreconciled", "unverifiable"]
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    # Stated closing balance minus the closing balance the transactions imply.
    reconciliation_difference_minor: int | None
    row_count: int
    imported_count: int
    duplicate_count: int
    categorization_status: Literal["pending", "done", "llm_unavailable"]
    uploaded_at: str


class Imported(BaseModel):
    # One per account found in the file (a PDF can hold checking and savings together).
    statements: list[Statement]


class PreviewTransaction(BaseModel):
    date: str
    amount_minor: int
    currency: Literal["USD", "INR"]
    description: str


class StatementPreview(BaseModel):
    row_count: int
    skipped_row_count: int
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    reconciliation_status: Literal["reconciled", "unreconciled", "unverifiable"]
    reconciliation_difference_minor: int | None
    transactions: list[PreviewTransaction]


class Transaction(BaseModel):
    id: int
    statement_id: int
    account_id: int
    account_name: str
    bank_id: str
    bank_name: str
    date: str
    amount_minor: int
    currency: Literal["USD", "INR"]
    description: str
    needs_review: bool
    category_id: int | None
    category_name: str | None
    category_source: Literal["rule", "cache", "llm", "user"] | None
    category_needs_review: bool


class CurrencyTotals(BaseModel):
    currency: Literal["USD", "INR"]
    money_in_minor: int
    money_out_minor: int  # a positive total of money out
    transaction_count: int


class MonthTotals(CurrencyTotals):
    month: str  # YYYY-MM


class CategoryTotals(CurrencyTotals):
    category_id: int | None  # None: not categorized yet
    category_name: str | None


class Summary(BaseModel):
    totals: list[CurrencyTotals]
    by_month: list[MonthTotals]
    by_category: list[CategoryTotals]


class TransactionUpdate(BaseModel):
    category_id: int


class RuleSuggestion(BaseModel):
    match_type: Literal["exact", "contains"]
    pattern: str
    category_id: int


class TransactionCorrected(BaseModel):
    transaction: Transaction
    # Offered to the user as "always categorize X as Y"; created only if they accept.
    suggested_rule: RuleSuggestion | None


class Category(BaseModel):
    id: int
    name: str
    region: Literal["US", "IN", "both"]
    is_default: bool
    excluded_from_spending: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    region: Literal["US", "IN", "both"] = "both"


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    excluded_from_spending: bool | None = None


class Rule(BaseModel):
    id: int
    match_type: Literal["exact", "contains"]
    pattern: str
    amount_min_minor: int | None
    amount_max_minor: int | None
    category_id: int
    category_name: str
    priority: int


class RuleCreate(BaseModel):
    match_type: Literal["exact", "contains"]
    pattern: str = Field(min_length=1, max_length=200)
    amount_min_minor: int | None = None
    amount_max_minor: int | None = None
    category_id: int
    priority: int = 0


class RuleUpdate(BaseModel):
    match_type: Literal["exact", "contains"] | None = None
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    amount_min_minor: int | None = None
    amount_max_minor: int | None = None
    category_id: int | None = None
    priority: int | None = None


class RuleCreated(BaseModel):
    rule: Rule
    # Existing transactions (never ones the user set by hand) moved to the rule's category.
    applied_count: int


PREVIEW_TRANSACTIONS = 20


def create_app(settings: Settings | None = None, frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        connection = db.connect(settings.database_path)
        try:
            db.migrate(connection)
        finally:
            connection.close()
        yield

    app = FastAPI(title="TheAccountant", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.llm = get_llm_provider(settings)
    install_error_handlers(app)
    max_upload_bytes = settings.max_upload_mb * 1024 * 1024

    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next):
        # Reject before the body is read, so an oversized upload is never buffered.
        content_length = request.headers.get("content-length", "")
        if content_length.isdigit() and int(content_length) > max_upload_bytes:
            return error_response(
                413, "payload_too_large", f"uploads are limited to {settings.max_upload_mb} MB"
            )
        return await call_next(request)

    @app.get("/api/health")
    def health(connection: Connection) -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "schema_version": db.schema_version(connection),
        }

    @app.get("/api/banks")
    def list_banks(connection: Connection) -> list[Bank]:
        return [Bank(**dict(row)) for row in db.list_banks(connection)]

    @app.post("/api/banks", status_code=201)
    def create_bank(body: BankCreate, connection: Connection) -> Bank:
        name = body.name.strip()
        bank_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if not bank_id:
            raise ApiError(422, "invalid_request", "name: must contain a letter or digit")
        date_format = body.default_date_format or DEFAULT_DATE_FORMAT_BY_COUNTRY[body.country]
        try:
            row = db.create_bank(
                connection,
                bank_id,
                name,
                body.country,
                CURRENCY_BY_COUNTRY[body.country],
                date_format,
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "bank_exists", f"a bank named {name!r} already exists") from None
        return Bank(**dict(row))

    @app.get("/api/accounts")
    def list_accounts(connection: Connection, bank_id: str | None = None) -> list[Account]:
        return [Account(**dict(row)) for row in db.list_accounts(connection, bank_id)]

    @app.post("/api/accounts", status_code=201)
    def create_account(body: AccountCreate, connection: Connection) -> Account:
        if db.get_bank(connection, body.bank_id) is None:
            raise ApiError(404, "bank_not_found", f"no bank with id {body.bank_id!r}")
        name = body.name.strip()
        try:
            row = db.create_account(connection, body.bank_id, body.type, name)
        except sqlite3.IntegrityError:
            raise ApiError(
                409, "account_exists", f"bank {body.bank_id!r} already has account {name!r}"
            ) from None
        return Account(**dict(row))

    @app.post("/api/statements/preview")
    def preview_statement(
        connection: Connection,
        file: Annotated[UploadFile, File()],
        account_id: Annotated[int, Form()],
        mapping: Annotated[str, Form()],
        password: Annotated[str | None, Form()] = None,
    ) -> StatementPreview:
        account = require_account(connection, account_id)
        rows = statement_rows(read_upload(file), account, password)
        confirmed = parse_mapping(mapping)
        parsed, skipped = apply_mapping_or_422(rows, confirmed, account["currency"])
        opening, closing, status, difference = check_balances(rows, confirmed, parsed, account)
        return StatementPreview(
            row_count=len(parsed),
            skipped_row_count=skipped,
            opening_balance_minor=opening,
            closing_balance_minor=closing,
            reconciliation_status=status,
            reconciliation_difference_minor=difference,
            transactions=[
                PreviewTransaction(
                    date=row.date,
                    amount_minor=row.amount_minor,
                    currency=account["currency"],
                    description=row.description,
                )
                for row in parsed[:PREVIEW_TRANSACTIONS]
            ],
        )

    @app.post("/api/statements", status_code=201)
    def upload_statement(
        connection: Connection,
        background: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        account_id: Annotated[int, Form()],
        mapping: Annotated[str | None, Form()] = None,
        password: Annotated[str | None, Form()] = None,
        remember: Annotated[bool, Form()] = True,
    ) -> Statement:
        data = read_upload(file)
        sha256 = hashlib.sha256(data).hexdigest()
        existing_id = db.find_statement_id_by_sha256(connection, sha256)
        if existing_id is not None:
            raise ApiError(
                409,
                "duplicate_statement",
                "this file was already imported",
                {"statement_id": existing_id},
            )
        account = require_account(connection, account_id)
        rows = statement_rows(data, account, password)
        if password and remember:
            # Only reached once the password opened the file, so a wrong one never
            # replaces the saved one.
            passwords.save_password(account["bank_id"], password)
        if mapping is not None:
            used = parse_mapping(mapping)
            parsed, _ = apply_mapping_or_422(rows, used, account["currency"])
        else:
            if account["csv_mapping"] is None:
                raise mapping_required(rows, account, "map the columns for this account")
            used = CsvMapping.model_validate_json(account["csv_mapping"])
            try:
                parsed, _ = csv_import.apply_mapping(rows, used, account["currency"])
            except CsvError as error:
                if error.code != "csv_mapping_invalid":
                    raise ApiError(422, error.code, str(error)) from None
                # The bank changed its export layout: ask again rather than guess.
                message = f"saved mapping no longer fits: {error}"
                raise mapping_required(rows, account, message) from None

        dates = [row.date for row in parsed]
        opening, closing, status, difference = check_balances(rows, used, parsed, account)
        statement_id = db.create_statement(
            connection,
            sha256=sha256,
            filename=file.filename or "statement",
            mime="application/pdf" if pdf.is_pdf(data) else "text/csv",
            file_bytes=data,
            account_id=account_id,
            currency=account["currency"],
            period_start=min(dates),
            period_end=max(dates),
            opening_balance_minor=opening,
            closing_balance_minor=closing,
            reconciliation_status=status,
            reconciliation_difference_minor=difference,
            transactions=csv_import.to_transactions(parsed, account_id),
        )
        if mapping is not None:
            # Saved only after the import succeeded with it: the user confirmed the preview.
            db.save_account_csv_mapping(connection, account_id, used.model_dump_json())
        # Categorizing can take a while with the LLM; the UI polls categorization_status.
        background.add_task(run_categorization, statement_id)
        return Statement(**dict(db.get_statement(connection, statement_id)))

    @app.post("/api/imports", status_code=201)
    def import_statement(
        connection: Connection,
        background: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        password: Annotated[str | None, Form()] = None,
        remember: Annotated[bool, Form()] = True,
    ) -> Imported:
        """Upload a statement and nothing else: the bank, accounts and layout are read from
        the file. Only an encrypted PDF can need something more: its password."""
        statement_ids = importer.import_file(
            connection,
            app.state.llm,
            filename=file.filename or "statement",
            data=read_upload(file),
            password=password,
            remember=remember,
            docling_models_path=settings.docling_models_path,
        )
        for statement_id in statement_ids:
            background.add_task(run_categorization, statement_id)
        return Imported(
            statements=[Statement(**dict(db.get_statement(connection, i))) for i in statement_ids]
        )

    @app.get("/api/statements")
    def list_statements(connection: Connection) -> list[Statement]:
        return [Statement(**dict(row)) for row in db.list_statements(connection)]

    @app.get("/api/statements/{statement_id}")
    def get_statement(statement_id: int, connection: Connection) -> Statement:
        row = db.get_statement(connection, statement_id)
        if row is None:
            raise ApiError(404, "statement_not_found", f"no statement with id {statement_id}")
        return Statement(**dict(row))

    @app.get("/api/transactions")
    def list_transactions(connection: Connection, filters: Filters) -> list[Transaction]:
        return [Transaction(**dict(row)) for row in db.list_transactions(connection, filters)]

    @app.get("/api/summary")
    def summary(connection: Connection, filters: Filters) -> Summary:
        groups = db.summarize_transactions(connection, filters)
        return Summary(
            totals=[CurrencyTotals(**dict(row)) for row in groups["totals"]],
            by_month=[MonthTotals(**dict(row)) for row in groups["by_month"]],
            by_category=[CategoryTotals(**dict(row)) for row in groups["by_category"]],
        )

    @app.post("/api/transactions/categorize", status_code=202)
    def categorize_pending(background: BackgroundTasks) -> dict:
        """Retry transactions left uncategorized, e.g. after Ollama was not running."""
        background.add_task(run_categorization, None)
        return {"status": "started"}

    @app.patch("/api/transactions/{transaction_id}")
    def correct_category(
        transaction_id: int, body: TransactionUpdate, connection: Connection
    ) -> TransactionCorrected:
        transaction = db.get_transaction(connection, transaction_id)
        if transaction is None:
            raise ApiError(404, "transaction_not_found", f"no transaction {transaction_id}")
        require_category(connection, body.category_id)
        db.add_category_assignments(connection, [(transaction_id, body.category_id, "user", False)])
        key = transaction["merchant_key"]
        suggestion = None
        if key:
            suggestion = RuleSuggestion(
                match_type="exact", pattern=key, category_id=body.category_id
            )
        return TransactionCorrected(
            transaction=Transaction(**dict(db.get_transaction(connection, transaction_id))),
            suggested_rule=suggestion,
        )

    @app.get("/api/categories")
    def list_categories(connection: Connection) -> list[Category]:
        return [Category(**dict(row)) for row in db.list_categories(connection)]

    @app.post("/api/categories", status_code=201)
    def create_category(body: CategoryCreate, connection: Connection) -> Category:
        name = body.name.strip()
        try:
            return Category(**dict(db.create_category(connection, name, body.region)))
        except sqlite3.IntegrityError:
            raise ApiError(409, "category_exists", f"a category named {name!r} exists") from None

    @app.patch("/api/categories/{category_id}")
    def update_category(category_id: int, body: CategoryUpdate, connection: Connection) -> Category:
        category = require_category(connection, category_id)
        if category["name"] == categorizer.UNCATEGORIZED:
            raise ApiError(409, "category_protected", "Uncategorized cannot be changed")
        name = body.name.strip() if body.name is not None else None
        try:
            db.update_category(
                connection,
                category_id,
                name=name,
                excluded_from_spending=body.excluded_from_spending,
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "category_exists", f"a category named {name!r} exists") from None
        return Category(**dict(db.get_category(connection, category_id)))

    @app.delete("/api/categories/{category_id}", status_code=204)
    def delete_category(category_id: int, connection: Connection) -> None:
        category = require_category(connection, category_id)
        if category["name"] == categorizer.UNCATEGORIZED:
            raise ApiError(409, "category_protected", "Uncategorized cannot be deleted")
        if db.category_in_use(connection, category_id):
            raise ApiError(
                409, "category_in_use", "move its transactions and rules to another category first"
            )
        db.delete_category(connection, category_id)

    @app.get("/api/rules")
    def list_rules(connection: Connection) -> list[Rule]:
        return [Rule(**dict(row)) for row in db.list_rules(connection)]

    @app.post("/api/rules", status_code=201)
    def create_rule(body: RuleCreate, connection: Connection) -> RuleCreated:
        require_category(connection, body.category_id)
        pattern = categorizer.merchant_key(body.pattern)
        if not pattern:
            raise ApiError(422, "invalid_request", "pattern: must contain a letter")
        rule = db.create_rule(
            connection,
            match_type=body.match_type,
            pattern=pattern,
            amount_min_minor=body.amount_min_minor,
            amount_max_minor=body.amount_max_minor,
            category_id=body.category_id,
            priority=body.priority,
        )
        # Apply to what is already imported, so the rule takes effect where the user sees it.
        moved = [
            (row["id"], rule["category_id"], "rule", False)
            for row in db.transactions_not_set_by_user(connection)
            if row["category_id"] != rule["category_id"]
            and categorizer.rule_matches(rule, row["merchant_key"], row["amount_minor"])
        ]
        db.add_category_assignments(connection, moved)
        return RuleCreated(rule=Rule(**dict(rule)), applied_count=len(moved))

    @app.patch("/api/rules/{rule_id}")
    def update_rule(rule_id: int, body: RuleUpdate, connection: Connection) -> Rule:
        if db.get_rule(connection, rule_id) is None:
            raise ApiError(404, "rule_not_found", f"no rule with id {rule_id}")
        changes = body.model_dump(exclude_unset=True)
        if "category_id" in changes:
            require_category(connection, changes["category_id"])
        if "pattern" in changes:
            changes["pattern"] = categorizer.merchant_key(changes["pattern"])
        db.update_rule(connection, rule_id, changes)
        return Rule(**dict(db.get_rule(connection, rule_id)))

    @app.delete("/api/rules/{rule_id}", status_code=204)
    def delete_rule(rule_id: int, connection: Connection) -> None:
        if db.get_rule(connection, rule_id) is None:
            raise ApiError(404, "rule_not_found", f"no rule with id {rule_id}")
        db.delete_rule(connection, rule_id)

    def run_categorization(statement_id: int | None) -> None:
        # A background task outlives the request, so it opens its own connection.
        connection = db.connect(settings.database_path)
        try:
            categorizer.categorize(connection, app.state.llm, statement_id)
        finally:
            connection.close()

    def require_category(connection: sqlite3.Connection, category_id: int) -> sqlite3.Row:
        category = db.get_category(connection, category_id)
        if category is None:
            raise ApiError(404, "category_not_found", f"no category with id {category_id}")
        return category

    def read_upload(file: UploadFile) -> bytes:
        # The middleware rejects large requests by Content-Length; this catches chunked ones.
        data = file.file.read(max_upload_bytes + 1)
        if len(data) > max_upload_bytes:
            raise ApiError(
                413, "payload_too_large", f"uploads are limited to {settings.max_upload_mb} MB"
            )
        return data

    def statement_rows(data: bytes, account: sqlite3.Row, password: str | None) -> list[list[str]]:
        if not pdf.is_pdf(data):
            try:
                return csv_import.read_rows(data)
            except CsvError as error:
                raise ApiError(422, error.code, str(error)) from None
        attempt = password or passwords.get_password(account["bank_id"])
        try:
            return pdf.read_rows(data, attempt, settings.docling_models_path)
        except PdfError as error:
            if error.code == "pdf_password_invalid" and not password:
                raise ApiError(
                    422,
                    "pdf_password_required",
                    "the saved password for this bank did not open this PDF",
                ) from None
            raise ApiError(422, error.code, str(error)) from None

    def require_account(connection: sqlite3.Connection, account_id: int) -> sqlite3.Row:
        account = db.get_account(connection, account_id)
        if account is None:
            raise ApiError(404, "account_not_found", f"no account with id {account_id}")
        return account

    def parse_mapping(mapping: str) -> CsvMapping:
        try:
            return CsvMapping.model_validate_json(mapping)
        except ValidationError as error:
            first = error.errors()[0]
            field = ".".join(str(part) for part in first["loc"]) or "mapping"
            raise ApiError(422, "csv_mapping_invalid", f"{field}: {first['msg']}") from None

    def apply_mapping_or_422(rows, mapping: CsvMapping, currency: str):
        try:
            return csv_import.apply_mapping(rows, mapping, currency)
        except CsvError as error:
            raise ApiError(422, error.code, str(error)) from None

    def check_balances(rows, mapping: CsvMapping, parsed, account: sqlite3.Row):
        currency = account["currency"]
        opening = find_balance(rows, mapping.opening_balance_label, currency, last=False)
        closing = find_balance(rows, mapping.closing_balance_label, currency, last=True)
        status, difference = reconcile(
            opening, closing, [row.amount_minor for row in parsed], account["type"]
        )
        return opening, closing, status, difference

    def mapping_required(rows, account: sqlite3.Row, message: str) -> ApiError:
        suggestion, source = layout.propose_layout(
            rows,
            app.state.llm,
            account_type=account["type"],
            currency=account["currency"],
            default_date_format=account["default_date_format"],
        )
        return ApiError(
            422,
            "csv_mapping_required",
            message,
            {
                "rows": rows[: csv_import.SAMPLE_ROWS],
                "suggested_mapping": suggestion,
                "suggestion_source": source,
                "date_formats": list(FORMATS),
            },
        )

    # The built UI is served from the same process; absent until the frontend is built.
    # Registered last so every /api route wins.
    if frontend_dist.is_dir():
        dist = frontend_dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            file = (dist / path).resolve()
            if path and file.is_file() and file.is_relative_to(dist):
                return FileResponse(file)
            # Client-side routes (/statements, /chat, ...) all load the app shell.
            return FileResponse(dist / "index.html")

    return app
