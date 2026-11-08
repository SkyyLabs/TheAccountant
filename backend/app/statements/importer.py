"""Import one uploaded file with no questions asked: find whose statement it is, read every
account in it, and store one statement per account. The only thing a file can still need
from the user is the password of an encrypted PDF.

Reading order for PDFs: transaction lines in the text (lines.py, most bank PDFs), then
tables (pdf.py with the layout proposal). CSVs go straight to the layout proposal.
"""

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.errors import ApiError
from app.llm.base import LlmProvider
from app.statements import csv_import, lines, passwords, pdf, understand
from app.statements.csv_import import CsvError, CsvMapping, ParsedRow
from app.statements.pdf import PdfError
from app.statements.reconciliation import find_balance, reconcile
from app.statements.understand import CURRENCY, Identity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Unlocked:
    password: str | None  # the one that opened the file, None if it was not encrypted
    typed: bool  # the user typed it in this request


def import_file(
    connection: sqlite3.Connection,
    provider: LlmProvider,
    *,
    filename: str,
    data: bytes,
    password: str | None,
    remember: bool,
    docling_models_path: Path,
) -> list[int]:
    """Store the file's statements and return their ids. Raises ApiError (409 duplicate,
    422 password needed or wrong, 422 statement_unreadable)."""
    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.statement_ids_for_file(connection, sha256)
    if existing:
        raise ApiError(
            409,
            "duplicate_statement",
            "this file was already imported",
            {"statement_ids": existing},
        )
    banks = {row["id"]: dict(row) for row in db.list_banks(connection)}
    store = _Store(connection, sha256=sha256, filename=filename, data=data)

    if pdf.is_pdf(data):
        unlocked = _unlock(data, password, banks)
        text = pdf.read_text(data, unlocked.password)
        identity = understand.identify(
            understand.statement_text([[line] for line in text.splitlines()], filename),
            provider,
            banks=banks,
        )
        statement_ids = _import_lines(store, identity, text, banks)
        if not statement_ids:
            rows = _pdf_rows(data, unlocked.password, docling_models_path)
            statement_ids = _import_rows(store, provider, rows, banks, filename)
        if unlocked.typed and remember:
            # Saved only after the password opened the file, under the bank it turned out to
            # be; a wrong password raised before this and never replaces a saved one.
            bank_id = db.get_account_bank(connection, store.first_account_id)
            passwords.save_password(bank_id, unlocked.password)
    else:
        try:
            rows = csv_import.read_rows(data)
        except CsvError as error:
            raise ApiError(422, error.code, str(error)) from None
        statement_ids = _import_rows(store, provider, rows, banks, filename)
    logger.info("import: statements=%d", len(statement_ids))
    return statement_ids


def _unlock(data: bytes, password: str | None, banks: dict[str, dict]) -> _Unlocked:
    if password:
        try:
            pdf.read_text(data, password)
        except PdfError as error:
            raise ApiError(422, error.code, str(error)) from None
        return _Unlocked(password, typed=True)
    saved = [passwords.get_password(bank_id) for bank_id in banks]
    # Not encrypted first, then every bank's saved password: the bank is not known yet.
    for candidate in [None, *(p for p in saved if p)]:
        try:
            pdf.read_text(data, candidate)
        except PdfError as error:
            if error.code not in ("pdf_password_required", "pdf_password_invalid"):
                raise ApiError(422, error.code, str(error)) from None
            continue
        return _Unlocked(candidate, typed=False)
    raise ApiError(422, "pdf_password_required", "this PDF needs a password")


def _pdf_rows(data: bytes, password: str | None, models_path: Path) -> list[list[str]]:
    try:
        return pdf.read_rows(data, password, models_path)
    except PdfError as error:
        if error.code == "pdf_no_tables":
            raise _unreadable() from None
        raise ApiError(422, error.code, str(error)) from None


def _unreadable() -> ApiError:
    return ApiError(
        422,
        "statement_unreadable",
        "no transactions could be found in this file",
    )


class _Store:
    """Creates banks, accounts and statements; the first statement stores the file."""

    def __init__(self, connection, *, sha256: str, filename: str, data: bytes) -> None:
        self.connection = connection
        self.sha256 = sha256
        self.filename = filename
        self.data = data
        self.file_id: int | None = None
        self.first_account_id: int | None = None

    def account_id(self, identity: Identity, last4: str | None, banks: dict[str, dict]) -> int:
        bank_id = identity.bank_id or self._other_bank(identity, banks)
        name = (
            f"••{last4}"
            if last4
            else ("Card" if identity.account_type == "credit_card" else "Account")
        )
        account_id = db.find_or_create_account(
            self.connection, bank_id, identity.account_type, name
        )
        self.first_account_id = self.first_account_id or account_id
        return account_id

    def _other_bank(self, identity: Identity, banks: dict[str, dict]) -> str:
        name = identity.bank_name or (
            "Unknown bank" if identity.country == "US" else "Unknown Indian bank"
        )
        bank_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if bank_id not in banks:
            try:
                db.create_bank(
                    self.connection,
                    bank_id,
                    name,
                    identity.country,
                    CURRENCY[identity.country],
                    understand.DEFAULT_DATE_FORMAT[identity.country],
                )
            except sqlite3.IntegrityError:
                pass  # same name under another id: reuse it below
            banks.update({row["id"]: dict(row) for row in db.list_banks(self.connection)})
        return (
            bank_id
            if bank_id in banks
            else next(b for b, bank in banks.items() if bank["name"] == name)
        )

    def statement(
        self,
        *,
        account_id: int,
        currency: str,
        parsed: list[ParsedRow],
        opening: int | None,
        closing: int | None,
        account_type: str,
        needs_review: set[int] = frozenset(),
    ) -> int:
        status, difference = reconcile(
            opening, closing, [row.amount_minor for row in parsed], account_type
        )
        if needs_review and status == "reconciled":
            status = "unreconciled"  # totals agree but some rows break the running balance
        transactions = csv_import.to_transactions(parsed, account_id)
        for transaction in transactions:
            transaction["needs_review"] = transaction["row_index"] in needs_review
        dates = [row.date for row in parsed]
        statement_id = db.create_statement(
            self.connection,
            sha256=self.sha256,
            filename=self.filename,
            mime="application/pdf" if pdf.is_pdf(self.data) else "text/csv",
            file_bytes=self.data,
            file_id=self.file_id,
            account_id=account_id,
            currency=currency,
            period_start=min(dates),
            period_end=max(dates),
            opening_balance_minor=opening,
            closing_balance_minor=closing,
            reconciliation_status=status,
            reconciliation_difference_minor=difference,
            transactions=transactions,
        )
        self.file_id = self.file_id or db.statement_file_id(self.connection, statement_id)
        return statement_id


def _import_lines(store: _Store, identity: Identity, text: str, banks) -> list[int]:
    currency = CURRENCY[identity.country]
    try:
        sections = lines.read_sections(text, currency=currency, day_first=identity.country == "IN")
    except lines.LinesError:
        return []
    statement_ids = []
    for section in sections:
        card = identity.account_type == "credit_card"
        # Without a running balance the printed sign is all there is; card statements print
        # charges as positive amounts, which are money out.
        invert = card and not section.has_running_balance
        parsed = [
            ParsedRow(
                row_index=index,
                date=t.date,
                amount_minor=-t.amount_minor if invert else t.amount_minor,
                description=t.description,
                raw_cells={"line": t.line},
            )
            for index, t in enumerate(section.transactions)
        ]
        account_id = store.account_id(
            identity, section.account_last4 or identity.account_last4, banks
        )
        statement_ids.append(
            store.statement(
                account_id=account_id,
                currency=currency,
                parsed=parsed,
                opening=section.opening_minor,
                closing=section.closing_minor,
                account_type=identity.account_type,
                needs_review={i for i, t in enumerate(section.transactions) if not t.fits_balance},
            )
        )
    return statement_ids


def _saved_layout(store: _Store, rows, banks, filename: str):
    """A known account (found by pattern, no LLM) whose saved layout still fits the file."""
    identity = understand.heuristic_identity(understand.statement_text(rows, filename), banks)
    if not (identity.bank_id and identity.account_last4):
        return None
    row = store.connection.execute(
        "SELECT id, type, csv_mapping FROM accounts WHERE bank_id = ? AND name = ?",
        (identity.bank_id, f"\u2022\u2022{identity.account_last4}"),
    ).fetchone()
    if row is None or row["csv_mapping"] is None:
        return None
    mapping = CsvMapping.model_validate_json(row["csv_mapping"])
    currency = banks[identity.bank_id]["currency"]
    try:
        parsed, _ = csv_import.apply_mapping(rows, mapping, currency)
    except CsvError:
        return None  # the bank changed its layout: read it afresh
    return row["id"], row["type"], currency, mapping, parsed


def _import_rows(store: _Store, provider: LlmProvider, rows, banks, filename: str) -> list[int]:
    known = _saved_layout(store, rows, banks, filename)
    if known is not None:
        account_id, account_type, currency, mapping, parsed = known
        store.first_account_id = store.first_account_id or account_id
    else:
        reading = understand.understand(rows, provider, banks=banks, filename=filename)
        if reading.mapping is None:
            raise _unreadable()
        account_type = reading.identity.account_type
        currency = CURRENCY[reading.identity.country]
        account_id = store.account_id(reading.identity, reading.identity.account_last4, banks)
        mapping = CsvMapping(**reading.mapping)
        parsed, _ = csv_import.apply_mapping(rows, mapping, currency)
        db.save_account_csv_mapping(store.connection, account_id, mapping.model_dump_json())
    opening = find_balance(rows, mapping.opening_balance_label, currency, last=False)
    closing = find_balance(rows, mapping.closing_balance_label, currency, last=True)
    return [
        store.statement(
            account_id=account_id,
            currency=currency,
            parsed=parsed,
            opening=opening,
            closing=closing,
            account_type=account_type,
        )
    ]
