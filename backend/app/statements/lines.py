"""Read statements whose transactions are lines of text (date, description, amount and often
a running balance), as most US bank PDFs are: no ruled table, no column headers to map.

Deterministic, no LLM:
- A transaction line starts with a date and ends with one or two money values (amount, then
  the running balance when there is one). A short line after it with neither is the rest of
  its description ("Card 9522").
- Dates without a year ("12/08") take it from the statement period, so a December to January
  statement gets both years right.
- One PDF can hold several accounts: each "Beginning/Opening/Previous Balance ...
  Ending/Closing/New Balance" stretch is one account, named by the nearest account number.
- With a running balance, the sign comes from the balance change, and every row is checked:
  previous balance + amount must equal the balance printed on that row.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.statements.money import AmountError, parse_amount

_MONEY = r"[-−]?\(?[$₹]?\s?-?\d[\d,]*\.\d{2}\)?(?:\s?(?:CR|DR|Cr|Dr))?"
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE = (
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?"
    rf"|\d{{1,2}}[ -](?:{_MONTHS})[a-z]*(?:[ -]\d{{2,4}})?"
    rf"|(?:{_MONTHS})[a-z]* \d{{1,2}}(?:,? \d{{4}})?"
)
_TRANSACTION = re.compile(
    rf"^(?P<date>{_DATE})\s+(?P<description>.*?)\s+(?P<first>{_MONEY})(?:\s+(?P<second>{_MONEY}))?$",
    re.IGNORECASE,
)
_OPENING = re.compile(
    rf"\b(?:beginning|opening|previous|starting)\s+balance\b.*?(?P<amount>{_MONEY})\s*$",
    re.IGNORECASE,
)
_CLOSING = re.compile(
    rf"\b(?:ending|closing|new)\s+balance\b.*?(?P<amount>{_MONEY})\s*$", re.IGNORECASE
)
_ACCOUNT_NUMBER = re.compile(
    r"(?:account|card)\s*(?:number|no\.?|#|ending\s+in)\s*:?\s*[\dx*• -]*?(\d{4})\b",
    re.IGNORECASE,
)
_PERIOD = re.compile(
    rf"(?P<start>(?:{_MONTHS})[a-z]*\.? \d{{1,2}},? \d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})"
    r"\s*(?:through|thru|to|-|–)\s*"
    rf"(?P<end>(?:{_MONTHS})[a-z]*\.? \d{{1,2}},? \d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})",
    re.IGNORECASE,
)
CONTINUATION_MAX_LENGTH = 40
# Page furniture that can follow a transaction at a page break; never part of a description.
_NOT_CONTINUATION = re.compile(r"\bpage \d+\b|\baccount\b|\bthrough\b|\bbalance\b", re.IGNORECASE)


@dataclass
class LineTransaction:
    date: str
    description: str
    amount_minor: int
    balance_minor: int | None
    line: str
    fits_balance: bool = True  # False: previous balance + amount != printed balance


@dataclass
class Section:
    account_last4: str | None
    opening_minor: int | None = None
    closing_minor: int | None = None
    transactions: list[LineTransaction] = field(default_factory=list)

    @property
    def has_running_balance(self) -> bool:
        return any(t.balance_minor is not None for t in self.transactions)


class LinesError(ValueError):
    pass


def _full_date(text: str, day_first: bool) -> date | None:
    text = text.replace(".", "").replace(",", "")
    formats = ["%B %d %Y", "%b %d %Y", "%d/%m/%Y" if day_first else "%m/%d/%Y"]
    for pattern in formats:
        try:
            return datetime.strptime(text.strip(), pattern).date()
        except ValueError:
            continue
    return None


def statement_period(text: str, day_first: bool) -> tuple[date, date] | None:
    for match in _PERIOD.finditer(text):
        start = _full_date(match["start"], day_first)
        end = _full_date(match["end"], day_first)
        if start and end and start <= end:
            return start, end
    return None


def _line_date(token: str, day_first: bool, period: tuple[date, date] | None) -> str | None:
    token = token.strip().lower()
    year: int | None = None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
            return date.fromisoformat(token).isoformat()
        numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", token)
        if numeric:
            first, second, year_text = numeric.groups()
            day, month = (int(first), int(second)) if day_first else (int(second), int(first))
            if year_text:
                year = int(year_text) + (2000 if len(year_text) == 2 else 0)
        else:
            parts = re.split(r"[ ,-]+", token)
            words = [p for p in parts if p.isalpha()]
            numbers = [int(p) for p in parts if p.isdigit()]
            month = datetime.strptime(words[0][:3], "%b").month
            day = numbers[0]
            if len(numbers) > 1:
                year = numbers[1] + (2000 if numbers[1] < 100 else 0)
        if year is not None:
            return date(year, month, day).isoformat()
        if period is None:
            return None
        start, end = period
        for candidate_year in (end.year, end.year - 1, end.year + 1):
            try:
                candidate = date(candidate_year, month, day)
            except ValueError:
                continue
            if start - timedelta(days=31) <= candidate <= end + timedelta(days=31):
                return candidate.isoformat()
        return None
    except (ValueError, IndexError):
        return None


def _money(token: str | None, currency: str) -> int | None:
    if token is None:
        return None
    try:
        return parse_amount(token.replace("−", "-").replace("$ ", "$"), currency)
    except AmountError:
        return None


def read_sections(text: str, *, currency: str, day_first: bool) -> list[Section]:
    """Every account section that has transactions, in document order. Raises LinesError if
    transaction lines exist but their dates cannot be placed in a year."""
    period = statement_period(text, day_first)
    sections: list[Section] = []
    loose = Section(account_last4=None)  # transactions outside any balance stretch (cards)
    current: Section | None = None
    account_last4: str | None = None
    last: LineTransaction | None = None
    first_opening: int | None = None
    last_closing: int | None = None

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        transaction = _TRANSACTION.match(line)
        if transaction:
            when = _line_date(transaction["date"], day_first, period)
            first = _money(transaction["first"], currency)
            second = _money(transaction["second"], currency)
            if first is not None:
                if when is None:
                    raise LinesError("transaction dates have no year and no statement period")
                last = LineTransaction(
                    date=when,
                    description=transaction["description"],
                    amount_minor=first,
                    balance_minor=second,
                    line=line,
                )
                (current or loose).transactions.append(last)
                continue
        # A continuation is only ever the line right after a transaction.
        previous, last = last, None
        number = _ACCOUNT_NUMBER.search(line)
        if number:
            account_last4 = number.group(1)  # transaction lines never name the account
        opening = _OPENING.search(line)
        if opening:
            current = Section(
                account_last4=account_last4, opening_minor=_money(opening["amount"], currency)
            )
            if first_opening is None:
                first_opening = current.opening_minor
            sections.append(current)
            continue
        closing = _CLOSING.search(line)
        if closing:
            amount = _money(closing["amount"], currency)
            last_closing = amount
            if current is not None:
                current.closing_minor = amount
                current = None
            continue
        if (
            previous is not None
            and len(line) <= CONTINUATION_MAX_LENGTH
            and not number
            and not _NOT_CONTINUATION.search(line)
        ):
            previous.description = f"{previous.description} {line}"

    found = [section for section in sections if section.transactions]
    if not found and loose.transactions:
        loose.account_last4 = account_last4
        loose.opening_minor = first_opening
        loose.closing_minor = last_closing
        found = [loose]
    return [_resolve_signs(_merge_same_account(s, found)) for s in _unique_accounts(found)]


def _unique_accounts(sections: list[Section]) -> list[Section]:
    seen: set[str | None] = set()
    unique = []
    for section in sections:
        if section.account_last4 not in seen or section.account_last4 is None:
            seen.add(section.account_last4)
            unique.append(section)
    return unique


def _merge_same_account(section: Section, sections: list[Section]) -> Section:
    if section.account_last4 is None:
        return section
    same = [s for s in sections if s.account_last4 == section.account_last4]
    return Section(
        account_last4=section.account_last4,
        opening_minor=same[0].opening_minor,
        closing_minor=same[-1].closing_minor,
        transactions=[t for s in same for t in s.transactions],
    )


def _resolve_signs(section: Section) -> Section:
    """With a running balance, the balance change gives the sign; rows that do not fit are
    marked, never adjusted."""
    if not section.has_running_balance:
        return section
    previous = section.opening_minor
    for transaction in section.transactions:
        if transaction.balance_minor is None or previous is None:
            transaction.fits_balance = False
            previous = None
            continue
        change = transaction.balance_minor - previous
        if abs(change) == abs(transaction.amount_minor):
            transaction.amount_minor = change
        else:
            transaction.fits_balance = False
        previous = transaction.balance_minor
    return section
