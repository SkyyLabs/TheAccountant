import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

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
