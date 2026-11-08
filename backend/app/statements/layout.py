"""First upload for an account: propose which line is the header, which columns hold what,
the date format and the balance labels.

The local LLM names the header line, the columns, the amount mode and the balance labels.
Code settles
everything it can check against the file: the header line is the row that holds the named
columns, the date format is the first that parses every row (the bank's default first, so an
all-ambiguous 03/04 file follows the bank), a card's sign makes most transactions money out,
and a label is kept only if a balance can be read after it. Header-name heuristics stand in
when the LLM is unavailable or wrong twice.

The LLM never supplies an amount or a date: the parsers read the values, and reconciliation
then checks the result mechanically.
"""

import logging

from pydantic import ValidationError

from app.llm.base import LlmError, LlmProvider, LlmUnavailable
from app.statements.csv_import import (
    CsvError,
    CsvMapping,
    amount_columns,
    apply_mapping,
    suggest_mapping,
)
from app.statements.dates import FORMATS, DateFormatError, parse_date
from app.statements.reconciliation import find_balance, reconcile

logger = logging.getLogger(__name__)

HEAD_LINES = 40
TAIL_LINES = 15
ATTEMPTS = 2  # one retry, then the heuristic

OPENING_LABELS = (
    "opening balance",
    "previous balance",
    "beginning balance",
    "starting balance",
    "balance brought forward",
    "balance b/f",
)
CLOSING_LABELS = (
    "closing balance",
    "new balance",
    "ending balance",
    "balance carried forward",
    "balance c/f",
)

SYSTEM = """You read exports of bank and credit-card statements.
The user shows the statement as numbered lines; cells are separated by " | ".
Identify the layout. Rules:
- header_line is the line number of the column header row of the transaction table.
- Column names must be copied exactly from that header line.
- amount_mode: "signed" if one amount column where negative is money out, "inverted" if one
  amount column where positive is money out (common for credit-card exports, where charges
  are positive), "debit_credit" if separate debit (money out) and credit (money in) columns.
- opening_balance_label and closing_balance_label are the exact words that introduce the
  statement's opening and closing balance (for cards: previous and new balance), or null if
  the statement shows none. Do not use a column header for these.
Answer with JSON only."""


def schema() -> dict:
    nullable_text = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {
            "header_line": {"type": "integer"},
            "date_column": {"type": "string"},
            "description_column": {"type": "string"},
            "amount_mode": {"enum": ["signed", "inverted", "debit_credit"]},
            "amount_column": nullable_text,
            "debit_column": nullable_text,
            "credit_column": nullable_text,
            "opening_balance_label": nullable_text,
            "closing_balance_label": nullable_text,
        },
        "required": [
            "header_line",
            "date_column",
            "description_column",
            "amount_mode",
            "amount_column",
            "debit_column",
            "credit_column",
            "opening_balance_label",
            "closing_balance_label",
        ],
    }


def prompt(rows: list[list[str]], account_type: str | None = None) -> str:
    numbered = [(index + 1, " | ".join(row)) for index, row in enumerate(rows)]
    shown = numbered
    if len(numbered) > HEAD_LINES + TAIL_LINES:
        shown = [*numbered[:HEAD_LINES], (None, "..."), *numbered[-TAIL_LINES:]]
    lines = "\n".join(text if number is None else f"{number}: {text}" for number, text in shown)
    if account_type is None:
        return f"Statement:\n{lines}"
    kind = "credit card" if account_type == "credit_card" else "bank account"
    return f"Statement of a {kind}:\n{lines}"


def _label_heuristic(rows: list[list[str]], labels: tuple[str, ...], currency: str, last: bool):
    for label in labels:
        if find_balance(rows, label, currency, last=last) is not None:
            return label
    return None


def _header_row(rows: list[list[str]], fields: dict, stated_line: object) -> int | None:
    named = {fields.get("date_column"), fields.get("description_column")}
    if None in named:
        return None
    if isinstance(stated_line, int) and 1 <= stated_line <= len(rows):
        if named <= set(rows[stated_line - 1]):
            return stated_line - 1
    return next((i for i, row in enumerate(rows) if named <= set(row)), None)


def _finish(
    fields: dict,
    rows: list[list[str]],
    *,
    stated_line: object,
    account_type: str,
    currency: str,
    default_date_format: str,
) -> dict | None:
    """A mapping that parses every row, with the checks above applied; None if impossible."""
    header_row = _header_row(rows, fields, stated_line)
    if header_row is None:
        return None
    fields = {**fields, "header_row": header_row}
    separate = fields.get("amount_mode") == "debit_credit"
    for unused in ("amount_column",) if separate else ("debit_column", "credit_column"):
        fields[unused] = None
    mapping, parsed = None, None
    # The bank's day/month order first: 03/04/26 at an Indian bank is 3 April, not 4 March.
    same_order_first = sorted(FORMATS, key=lambda name: name[:2] != default_date_format[:2])
    for date_format in dict.fromkeys([default_date_format, *same_order_first]):
        if date_format not in FORMATS:
            continue
        try:
            candidate = CsvMapping(**{**fields, "date_format": date_format})
            parsed, _ = apply_mapping(rows, candidate, currency)
        except (ValidationError, CsvError, TypeError):
            continue
        mapping = candidate
        break
    if mapping is None:
        return None
    if account_type == "credit_card" and mapping.amount_mode in ("signed", "inverted"):
        money_in = sum(1 for row in parsed if row.amount_minor > 0)
        flipped = money_in > len(parsed) - money_in
        if flipped:
            mode = "signed" if mapping.amount_mode == "inverted" else "inverted"
            mapping = mapping.model_copy(update={"amount_mode": mode})
    proposal = mapping.model_dump()
    for key, labels, last in (
        ("opening_balance_label", OPENING_LABELS, False),
        ("closing_balance_label", CLOSING_LABELS, True),
    ):
        if find_balance(rows, proposal[key], currency, last=last) is None:
            proposal[key] = _label_heuristic(rows, labels, currency, last)
    return proposal


def _dated_rows_skipped(rows: list[list[str]], mapping: dict, currency: str) -> int:
    """Rows with a readable date that the mapping still skipped for having no amount: a
    sign of a misread amount column (e.g. "Money Out" taken as the only amount)."""
    parsed, _ = apply_mapping(rows, CsvMapping(**mapping), currency)
    headers = rows[mapping["header_row"]]
    date_index = headers.index(mapping["date_column"])
    dated = 0
    for row in rows[mapping["header_row"] + 1 :]:
        cell = row[date_index] if date_index < len(row) else ""
        try:
            parse_date(cell, mapping["date_format"])
        except DateFormatError:
            continue
        dated += 1
    return dated - len(parsed)


def _best(candidates: list[dict | None], rows, account_type: str, currency: str) -> dict | None:
    """Prefer a layout whose balances reconcile, then one that skips no dated rows; the
    first candidate (the LLM's) wins ties."""

    def score(mapping: dict) -> tuple[bool, int]:
        parsed, _ = apply_mapping(rows, CsvMapping(**mapping), currency)
        opening = find_balance(rows, mapping["opening_balance_label"], currency, last=False)
        closing = find_balance(rows, mapping["closing_balance_label"], currency, last=True)
        status, _ = reconcile(opening, closing, [r.amount_minor for r in parsed], account_type)
        return (status == "reconciled", -_dated_rows_skipped(rows, mapping, currency))

    valid = [mapping for mapping in candidates if mapping is not None]
    return max(valid, key=score) if valid else None


def finish_answer(
    answer: dict,
    rows: list[list[str]],
    *,
    account_type: str,
    currency: str,
    default_date_format: str,
) -> dict | None:
    """The better of the LLM's layout and the header-name guess, each checked against every
    row; None if neither parses."""
    fields = {key: value for key, value in answer.items() if key in CsvMapping.model_fields}
    from_llm = _finish(
        fields,
        rows,
        stated_line=answer.get("header_line"),
        account_type=account_type,
        currency=currency,
        default_date_format=default_date_format,
    )
    if from_llm is None:
        return None
    # Same header line and columns, amount columns from the header names instead.
    amounts_by_name = _finish(
        {**from_llm, **amount_columns(rows[from_llm["header_row"]])},
        rows,
        stated_line=from_llm["header_row"] + 1,
        account_type=account_type,
        currency=currency,
        default_date_format=default_date_format,
    )
    guessed = checked_heuristic_layout(
        rows, account_type=account_type, currency=currency, default_date_format=default_date_format
    )
    return _best([from_llm, amounts_by_name, guessed], rows, account_type, currency)


def checked_heuristic_layout(
    rows: list[list[str]], *, account_type: str, currency: str, default_date_format: str
) -> dict | None:
    """The header-name guess, only if it parses every row."""
    suggestion = suggest_mapping(rows, default_date_format)
    return _finish(
        suggestion,
        rows,
        stated_line=suggestion["header_row"] + 1,
        account_type=account_type,
        currency=currency,
        default_date_format=default_date_format,
    )


def heuristic_layout(
    rows: list[list[str]], *, account_type: str, currency: str, default_date_format: str
) -> dict:
    suggestion = suggest_mapping(rows, default_date_format)
    finished = _finish(
        suggestion,
        rows,
        stated_line=suggestion["header_row"] + 1,
        account_type=account_type,
        currency=currency,
        default_date_format=default_date_format,
    )
    if finished is not None:
        return finished
    # Incomplete guess: the user fills the gaps in the form.
    suggestion["opening_balance_label"] = _label_heuristic(rows, OPENING_LABELS, currency, False)
    suggestion["closing_balance_label"] = _label_heuristic(rows, CLOSING_LABELS, currency, True)
    return suggestion


def propose_layout(
    rows: list[list[str]],
    provider: LlmProvider,
    *,
    account_type: str,
    currency: str,
    default_date_format: str,
) -> tuple[dict, str]:
    """Return (suggested mapping, source) where source is "llm" or "heuristic"."""
    question = prompt(rows, account_type)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            answer = provider.complete_json(SYSTEM, question, schema())
        except LlmUnavailable:
            logger.info("layout proposal: llm unavailable, using heuristic")
            break
        except LlmError:
            answer = {}
        proposal = finish_answer(
            answer,
            rows,
            account_type=account_type,
            currency=currency,
            default_date_format=default_date_format,
        )
        if proposal is not None:
            logger.info("layout proposal: llm accepted attempt=%d rows=%d", attempt, len(rows))
            return proposal, "llm"
        logger.info("layout proposal: llm rejected attempt=%d", attempt)
    suggestion = heuristic_layout(
        rows, account_type=account_type, currency=currency, default_date_format=default_date_format
    )
    return suggestion, "heuristic"
