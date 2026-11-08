"""CSV statements: suggest a column mapping, apply a confirmed one, fingerprint the rows.

Amounts and dates are read by the parsers in money.py and dates.py with the mapping's
declared date format. A row that cannot be read stops the import. Rows with no date or no
amount at all (preamble, footers, opening-balance lines) are skipped and counted, so the
preview shows how many there were.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.statements.dates import FORMATS, DateFormatError, parse_date
from app.statements.money import AmountError, parse_amount

# How far down the file to look for the header row; bank exports put a preamble above it.
HEADER_SEARCH_ROWS = 30
SAMPLE_ROWS = 30

DATE_HEADERS = ("transaction date", "txn date", "trans. date", "date", "posting date", "post date")
DESCRIPTION_HINTS = ("description", "narration", "particulars", "details", "remarks", "memo")
DEBIT_HINTS = ("debit", "withdrawal")
CREDIT_HINTS = ("credit", "deposit")


class CsvMapping(BaseModel):
    """Which columns hold what. Columns are referenced by their header text."""

    header_row: int = Field(ge=0)
    date_column: str
    description_column: str
    # signed: the column's own sign. inverted: positive means money out (many card exports).
    # debit_credit: separate columns, debit is money out.
    amount_mode: Literal["signed", "inverted", "debit_credit"]
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    date_format: str

    @field_validator("date_format")
    @classmethod
    def known_date_format(cls, value: str) -> str:
        if value not in FORMATS:
            raise ValueError(f"must be one of {', '.join(FORMATS)}")
        return value

    @model_validator(mode="after")
    def amount_columns_match_mode(self) -> "CsvMapping":
        if self.amount_mode == "debit_credit":
            if not (self.debit_column and self.credit_column):
                raise ValueError("debit_credit needs debit_column and credit_column")
        elif not self.amount_column:
            raise ValueError(f"{self.amount_mode} needs amount_column")
        return self


class CsvError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedRow:
    row_index: int
    date: str
    amount_minor: int
    description: str
    raw_cells: dict[str, str]


def read_rows(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError("csv_unreadable", "the file is not UTF-8 text") from None
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as error:
        raise CsvError("csv_unreadable", f"not a readable CSV file: {error}") from None
    rows = [[cell.strip() for cell in row] for row in rows]
    if not any(any(row) for row in rows):
        raise CsvError("csv_unreadable", "the file has no rows")
    return rows


def suggest_mapping(rows: list[list[str]], default_date_format: str) -> dict:
    """Best-effort guess from header names. Fields it cannot guess are None; the user
    confirms or corrects every field in the preview before anything is saved."""
    header_row = next(
        (
            index
            for index, row in enumerate(rows[:HEADER_SEARCH_ROWS])
            if any("date" in cell.lower() for cell in row)
        ),
        0,
    )
    headers = [cell for cell in rows[header_row] if cell]
    lowered = {header: header.lower() for header in headers}

    def first(predicate) -> str | None:
        return next((header for header in headers if predicate(lowered[header])), None)

    date_column = next(
        (header for wanted in DATE_HEADERS for header in headers if lowered[header] == wanted),
        None,
    ) or first(lambda name: "date" in name)
    debit_column = first(lambda name: any(hint in name for hint in DEBIT_HINTS))
    credit_column = first(lambda name: any(hint in name for hint in CREDIT_HINTS))
    separate = bool(debit_column and credit_column and debit_column != credit_column)
    return {
        "header_row": header_row,
        "date_column": date_column,
        "description_column": first(lambda name: any(h in name for h in DESCRIPTION_HINTS)),
        "amount_mode": "debit_credit" if separate else "signed",
        "amount_column": None if separate else first(lambda name: "amount" in name),
        "debit_column": debit_column if separate else None,
        "credit_column": credit_column if separate else None,
        "date_format": default_date_format,
    }


def apply_mapping(
    rows: list[list[str]], mapping: CsvMapping, currency: str
) -> tuple[list[ParsedRow], int]:
    """Parse every data row. Returns the rows and how many were skipped (no date or amount)."""
    if mapping.header_row >= len(rows):
        raise CsvError("csv_mapping_invalid", f"header_row {mapping.header_row} is past the end")
    headers = rows[mapping.header_row]

    def column_index(name: str) -> int:
        if headers.count(name) != 1:
            found = "appears more than once" if name in headers else "is not in the header row"
            raise CsvError("csv_mapping_invalid", f"column {name!r} {found}")
        return headers.index(name)

    date_index = column_index(mapping.date_column)
    description_index = column_index(mapping.description_column)
    if mapping.amount_mode == "debit_credit":
        debit_index = column_index(mapping.debit_column)
        credit_index = column_index(mapping.credit_column)
        amount_indexes = (debit_index, credit_index)
    else:
        amount_index = column_index(mapping.amount_column)
        amount_indexes = (amount_index,)

    parsed: list[ParsedRow] = []
    skipped = 0
    for offset, row in enumerate(rows[mapping.header_row + 1 :]):
        line_number = mapping.header_row + 2 + offset
        if not any(row):
            continue
        cells = row + [""] * (len(headers) - len(row))
        if not cells[date_index] or not any(cells[i] for i in amount_indexes):
            skipped += 1
            continue
        try:
            date = parse_date(cells[date_index], mapping.date_format)
            if mapping.amount_mode == "debit_credit":
                debit, credit = cells[debit_index], cells[credit_index]
                if bool(debit) == bool(credit):
                    raise AmountError("needs exactly one of debit or credit")
                amount_minor = (
                    -parse_amount(debit, currency) if debit else parse_amount(credit, currency)
                )
            else:
                amount_minor = parse_amount(cells[amount_index], currency)
                if mapping.amount_mode == "inverted":
                    amount_minor = -amount_minor
        except (DateFormatError, AmountError) as error:
            raise CsvError("csv_row_invalid", f"row {line_number}: {error}") from None
        parsed.append(
            ParsedRow(
                row_index=len(parsed),
                date=date,
                amount_minor=amount_minor,
                description=cells[description_index],
                raw_cells={header: cells[i] for i, header in enumerate(headers) if header},
            )
        )
    if not parsed:
        raise CsvError("csv_row_invalid", "no transactions found under the header row")
    return parsed, skipped


def normalize_description(description: str) -> str:
    return " ".join(description.lower().split())


def to_transactions(parsed: list[ParsedRow], account_id: int) -> list[dict]:
    """Add the fingerprint that de-duplicates across overlapping statements.

    The occurrence number (how many identical rows came earlier in this statement) keeps
    genuine same-day duplicates within one statement, while the same rows in an
    overlapping statement produce the same fingerprints and are skipped.
    """
    seen: dict[tuple, int] = {}
    transactions = []
    for row in parsed:
        normalized = normalize_description(row.description)
        key = (row.date, row.amount_minor, normalized)
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        identity = f"{account_id}|{row.date}|{row.amount_minor}|{normalized}|{occurrence}"
        transactions.append(
            {
                "row_index": row.row_index,
                "date": row.date,
                "amount_minor": row.amount_minor,
                "description": row.description,
                "normalized_description": normalized,
                "raw_row": json.dumps(row.raw_cells, ensure_ascii=False),
                "fingerprint": hashlib.sha256(identity.encode()).hexdigest(),
            }
        )
    return transactions
