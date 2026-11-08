import datetime
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
from pydantic import BaseModel, Field

from app import __version__, db
from app.categorize import categorizer
from app.config import REPO_ROOT, Settings
from app.errors import ApiError, error_response, install_error_handlers
from app.llm import get_llm_provider
from app.statements import importer
from app.statements.money import AmountError, parse_amount

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


class Account(BaseModel):
    id: int
    bank_id: str
    bank_name: str
    type: Literal["bank", "credit_card"]
    name: str


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


class Import(BaseModel):
    """An uploaded file and the local LLM's progress reading it."""

    id: int
    filename: str
    status: Literal["processing", "done", "failed"]
    progress_done: int  # parts of the statement read so far
    progress_total: int
    error: str | None  # plain-language reason when failed
    rejected_count: int  # transactions the model returned without a usable date or amount
    uploaded_at: str
    statements: list[Statement]  # one per account found in the file


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

    @app.get("/api/accounts")
    def list_accounts(connection: Connection, bank_id: str | None = None) -> list[Account]:
        return [Account(**dict(row)) for row in db.list_accounts(connection, bank_id)]

    @app.post("/api/imports", status_code=202)
    def upload(
        connection: Connection,
        background: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        password: Annotated[str | None, Form()] = None,
        remember: Annotated[bool, Form()] = True,
    ) -> Import:
        """Upload a statement and nothing else. The local LLM reads it in the background;
        poll GET /api/imports/{id}. Only an encrypted PDF can need more: its password."""
        started = importer.start_import(
            connection,
            filename=file.filename or "statement",
            data=read_upload(file),
            password=password,
            remember=remember,
        )
        background.add_task(
            importer.run_import,
            settings.database_path,
            app.state.llm,
            started,
            docling_models_path=settings.docling_models_path,
        )
        return import_of(connection, started.import_id)

    @app.get("/api/imports")
    def list_imports(connection: Connection) -> list[Import]:
        return [import_of(connection, row["id"]) for row in db.list_imports(connection)]

    @app.get("/api/imports/{import_id}")
    def get_import(import_id: int, connection: Connection) -> Import:
        if db.get_import(connection, import_id) is None:
            raise ApiError(404, "import_not_found", f"no import with id {import_id}")
        return import_of(connection, import_id)

    def import_of(connection: sqlite3.Connection, import_id: int) -> Import:
        statements = [
            Statement(**dict(row)) for row in db.statements_of_import(connection, import_id)
        ]
        return Import(**dict(db.get_import(connection, import_id)), statements=statements)

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
