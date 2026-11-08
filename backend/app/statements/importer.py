"""Import an uploaded file with no questions asked, in two steps:

1. start_import (in the request): duplicate check and, for an encrypted PDF, the password,
   since only the user can supply it. The file is stored as an import in progress.
2. run_import (in the background): text of the file, the local LLM reads it (extract.py,
   verified against the text), one statement per account found, then categorization.
   Progress and a plain-language failure reason are kept on the import for the UI.
"""

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.categorize import categorizer
from app.chat.merchants import embed_new_merchants
from app.errors import ApiError
from app.llm.base import LlmError, LlmProvider, LlmUnavailable
from app.statements import passwords, pdf
from app.statements.extract import NothingFound, extract
from app.statements.fingerprints import fingerprinted
from app.statements.reconciliation import reconcile

logger = logging.getLogger(__name__)

COUNTRY_OF = {"USD": "US", "INR": "IN"}


@dataclass(frozen=True)
class Started:
    import_id: int
    # In memory only, for the background step: never stored. typed_password is saved to the
    # Keychain under the bank found in the file, once the file has been read.
    password: str | None
    typed_password: bool
    remember: bool


def start_import(
    connection: sqlite3.Connection,
    *,
    filename: str,
    data: bytes,
    password: str | None,
    remember: bool,
) -> Started:
    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.find_import_by_sha256(connection, sha256)
    if existing is not None and existing["status"] == "failed":
        db.delete_failed_import(connection, existing["id"])  # let the user try again
    elif existing is not None:
        raise ApiError(
            409,
            "duplicate_statement",
            "this file was already uploaded",
            {"import_id": existing["id"]},
        )
    opened_with, typed = None, False
    if pdf.is_pdf(data):
        opened_with, typed = _password_that_opens(connection, data, password)
    elif not _looks_like_text(data):
        raise ApiError(415, "unsupported_file_type", "upload a PDF or CSV statement")
    import_id = db.create_import(
        connection,
        sha256=sha256,
        filename=filename,
        mime="application/pdf" if pdf.is_pdf(data) else "text/csv",
        file_bytes=data,
    )
    return Started(import_id, opened_with, typed, remember)


def _looks_like_text(data: bytes) -> bool:
    try:
        data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _password_that_opens(
    connection: sqlite3.Connection, data: bytes, password: str | None
) -> tuple[str | None, bool]:
    if password:
        try:
            pdf.unlock(data, password)
        except pdf.PdfError as error:
            raise ApiError(422, error.code, str(error)) from None
        return password, True
    saved = [passwords.get_password(row["id"]) for row in db.list_banks(connection)]
    # Not encrypted first, then every saved password: which bank it is is not known yet.
    for candidate in [None, *(p for p in saved if p)]:
        try:
            pdf.unlock(data, candidate)
        except pdf.PdfError as error:
            if error.code == "pdf_unreadable":
                raise ApiError(422, error.code, str(error)) from None
            continue
        return candidate, False
    raise ApiError(422, "pdf_password_required", "this PDF needs a password")


def run_import(
    database_path: Path,
    provider: LlmProvider,
    started: Started,
    *,
    docling_models_path: Path,
) -> None:
    """The background step. Never raises: a failure is recorded on the import."""
    connection = db.connect(database_path)
    try:
        _run(connection, provider, started, docling_models_path)
    except LlmUnavailable:
        _fail(connection, started, "The local AI is not running. Start Ollama and upload again.")
    except NothingFound:
        _fail(connection, started, "No transactions were found in this file.")
    except pdf.PdfError as error:
        _fail(connection, started, str(error).capitalize() + ".")
    except Exception:
        logger.exception("import %d failed", started.import_id)
        _fail(connection, started, "Something went wrong reading this file.")
    finally:
        connection.close()


def _fail(connection: sqlite3.Connection, started: Started, reason: str) -> None:
    db.finish_import(connection, started.import_id, status="failed", error=reason)


def _run(connection, provider, started: Started, models_path: Path) -> None:
    data = db.import_file_bytes(connection, started.import_id)
    if pdf.is_pdf(data):
        text = pdf.text_of(pdf.unlock(data, started.password), models_path)
    else:
        text = data.decode("utf-8-sig", errors="replace")

    def progress(done: int, total: int) -> None:
        db.set_import_progress(connection, started.import_id, done, total)

    extraction = extract(text, provider, progress=progress)
    statement_ids = []
    for index, account in enumerate(extraction.accounts):
        transactions = [t for t in extraction.transactions if t.account_index == index]
        if not transactions:
            continue
        country = COUNTRY_OF[account.currency]
        bank_id = db.find_or_create_bank(
            connection, account.bank_name or "Unknown bank", country, account.currency
        )
        name = (
            f"••{account.account_last4}"
            if account.account_last4
            else ("Card" if account.account_type == "credit_card" else "Account")
        )
        account_id = db.find_or_create_account(connection, bank_id, account.account_type, name)
        amounts = [t.amount_minor for t in transactions]
        status, difference = reconcile(
            account.opening_minor, account.closing_minor, amounts, account.account_type
        )
        rows = fingerprinted(
            [
                {
                    "date": t.date,
                    "amount_minor": t.amount_minor,
                    "description": t.description,
                    "needs_review": not t.verified,
                    "raw": {"source": "llm", "verified": t.verified},
                }
                for t in transactions
            ],
            account_id,
        )
        dates = [t.date for t in transactions]
        statement_ids.append(
            db.create_statement(
                connection,
                sha256="",
                filename="",
                mime="",
                file_bytes=b"",
                file_id=started.import_id,
                account_id=account_id,
                currency=account.currency,
                period_start=min(dates),
                period_end=max(dates),
                opening_balance_minor=account.opening_minor,
                closing_balance_minor=account.closing_minor,
                reconciliation_status=status,
                reconciliation_difference_minor=difference,
                transactions=rows,
            )
        )
        if started.typed_password and started.remember:
            passwords.save_password(bank_id, started.password)
    for statement_id in statement_ids:
        categorizer.categorize(connection, provider, statement_id)
    try:
        embed_new_merchants(connection, provider)  # ready for chat's merchant search
    except LlmError:
        logger.info(
            "import %d: merchants not embedded, done before the next search", started.import_id
        )
    # Done only once categorized, so the dashboard opens on finished figures.
    db.finish_import(
        connection, started.import_id, status="done", rejected_count=extraction.rejected
    )
    logger.info(
        "import %d: statements=%d transactions=%d rejected=%d",
        started.import_id,
        len(statement_ids),
        len(extraction.transactions),
        extraction.rejected,
    )
