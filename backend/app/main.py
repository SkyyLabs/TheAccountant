import re
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app import __version__, db
from app.config import REPO_ROOT, Settings
from app.errors import ApiError, install_error_handlers
from app.statements.dates import FORMATS

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
    install_error_handlers(app)

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
