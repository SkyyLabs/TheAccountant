import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from app import __version__, db
from app.config import REPO_ROOT, Settings
from app.errors import ApiError, error_response, install_error_handlers
from app.llm import get_llm_provider
from app.statements import csv_import, layout, passwords, pdf
from app.statements.csv_import import CsvError, CsvMapping
from app.statements.dates import FORMATS
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
    uploaded_at: str


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
        return Statement(**dict(db.get_statement(connection, statement_id)))

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
    def list_transactions(connection: Connection) -> list[Transaction]:
        return [Transaction(**dict(row)) for row in db.list_transactions(connection)]

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
