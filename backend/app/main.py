import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app import __version__, db
from app.config import REPO_ROOT, Settings
from app.errors import install_error_handlers

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


def create_app(settings: Settings | None = None) -> FastAPI:
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

    # The built UI is served from the same process; absent until the frontend is built.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app
