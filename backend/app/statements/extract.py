"""The local LLM reads a statement's text; code verifies what it returns against that text.

Any bank, any card, any layout: there is no per-format code. The LLM extracts the accounts
in the statement (bank, last 4 digits, bank account or card, currency, opening and closing
balance, period) and every transaction (date, description, amount, money in or out).

Code then checks each answer against the source text, never trusting it blindly:
- every amount must be a money value that appears in the text it came from;
- every date must be a real date inside the statement period (when there is one);
- balances must appear in the text, and opening + transactions must equal closing.
What fails a check is kept but flagged for review (a transaction without a usable date or
amount cannot be stored and is counted as rejected). Amounts are integer minor units from
parse_amount, never floats.
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.llm.base import LlmError, LlmProvider, LlmUnavailable
from app.statements.money import AmountError, parse_amount

logger = logging.getLogger(__name__)

CHUNK_CHARS = 3500  # one LLM call per chunk of statement text, split at line ends
HEAD_LINES = 80
TAIL_LINES = 40
ATTEMPTS = 2
PERIOD_SLACK = timedelta(days=31)
CURRENCIES = ("USD", "INR")
_MONEY = re.compile(r"\d[\d,]*\.\d{2}")

STATEMENT_SYSTEM = """You read bank and credit-card statements of a person in the US or India.
From the statement text, list each account it covers (one PDF can cover checking and savings,
or several cards) and the statement period. For each account:
- bank_name: the bank or card issuer as written in the statement, or null.
- account_last4: last 4 digits of the account or card number as written, or null.
- account_type: "credit_card" for a card, otherwise "bank".
- currency: "USD" or "INR".
- opening_balance / closing_balance: copied exactly as printed (for cards: previous and new
  balance), or null if not shown.
period_start / period_end: the statement period as YYYY-MM-DD, or null.
Answer with JSON only."""

TRANSACTIONS_SYSTEM = """You extract transactions from part of a bank or credit-card statement.
List every transaction in the text below, in order. Do not list balances, totals, summaries,
interest rates, fees schedules or anything that is not a single dated transaction.
For each transaction:
- date: YYYY-MM-DD. When the statement prints no year, use the statement period to choose it.
- description: the transaction text as printed, on one line.
- amount: the amount copied exactly as printed, without the sign.
- direction: "out" for money leaving the account (purchases, withdrawals, payments made,
  debits, charges on a card), "in" for money coming in (deposits, salary, refunds, credits,
  payments received on a card).
- account_last4: which account it belongs to, from the list given, or null.
If the text has no transactions, return an empty list. Answer with JSON only."""


@dataclass
class Account:
    bank_name: str | None
    account_last4: str | None
    account_type: str  # "bank" or "credit_card"
    currency: str
    opening_minor: int | None
    closing_minor: int | None


@dataclass
class Transaction:
    account_index: int
    date: str
    description: str
    amount_minor: int
    verified: bool  # False: the amount or date did not check out against the text


@dataclass
class Extraction:
    accounts: list[Account]
    period: tuple[date, date] | None
    transactions: list[Transaction] = field(default_factory=list)
    rejected: int = 0  # transactions returned without a usable date or amount


class NothingFound(ValueError):
    pass


def money_values(text: str) -> set[int]:
    """Every money-looking value in the text, as positive minor units (2 decimals)."""
    return {int(m.group().replace(",", "").replace(".", "")) for m in _MONEY.finditer(text)}


def _amount(text: object, currency: str) -> int | None:
    if not isinstance(text, str | int | float):
        return None
    try:
        return abs(parse_amount(str(text).replace("−", "-"), currency))
    except AmountError:
        return None


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def chunks(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if current and size + len(line) > CHUNK_CHARS:
            parts.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append("\n".join(current))
    return parts


def _ask(provider: LlmProvider, system: str, prompt: str, schema: dict) -> dict:
    """One retry on an unusable answer; LlmUnavailable propagates."""
    for _ in range(ATTEMPTS):
        try:
            return provider.complete_json(system, prompt, schema)
        except LlmUnavailable:
            raise
        except LlmError:
            continue
    return {}


def _statement_schema() -> dict:
    text = {"type": ["string", "null"]}
    account = {
        "type": "object",
        "properties": {
            "bank_name": text,
            "account_last4": text,
            "account_type": {"enum": ["bank", "credit_card"]},
            "currency": {"enum": list(CURRENCIES)},
            "opening_balance": text,
            "closing_balance": text,
        },
        "required": [
            "bank_name",
            "account_last4",
            "account_type",
            "currency",
            "opening_balance",
            "closing_balance",
        ],
    }
    return {
        "type": "object",
        "properties": {
            "accounts": {"type": "array", "items": account},
            "period_start": text,
            "period_end": text,
        },
        "required": ["accounts", "period_start", "period_end"],
    }


def _transactions_schema() -> dict:
    item = {
        "type": "object",
        "properties": {
            "date": {"type": "string"},
            "description": {"type": "string"},
            "amount": {"type": "string"},
            "direction": {"enum": ["in", "out"]},
            "account_last4": {"type": ["string", "null"]},
        },
        "required": ["date", "description", "amount", "direction", "account_last4"],
    }
    return {
        "type": "object",
        "properties": {"transactions": {"type": "array", "items": item}},
        "required": ["transactions"],
    }


def _accounts(answer: dict, text: str) -> list[Account]:
    lowered = text.lower()
    values = money_values(text)
    accounts = []
    for item in answer.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        currency = item.get("currency") if item.get("currency") in CURRENCIES else "USD"
        name = item.get("bank_name")
        name = name.strip() if isinstance(name, str) and name.strip() else None
        last4 = item.get("account_last4")
        balances = []
        for key in ("opening_balance", "closing_balance"):
            raw = item.get(key)
            minor = _amount(raw, currency)
            # Kept only if that value is printed in the statement; its sign as printed.
            if minor is not None and minor in values:
                balances.append(parse_amount(str(raw).replace("−", "-"), currency))
            else:
                balances.append(None)
        accounts.append(
            Account(
                # Names and numbers the statement does not contain were made up: dropped.
                bank_name=name if name and name.lower() in lowered else None,
                account_last4=last4
                if isinstance(last4, str) and re.fullmatch(r"\d{4}", last4) and last4 in text
                else None,
                account_type="credit_card" if item.get("account_type") == "credit_card" else "bank",
                currency=currency,
                opening_minor=balances[0],
                closing_minor=balances[1],
            )
        )
    return accounts


def _period(answer: dict) -> tuple[date, date] | None:
    start, end = _iso(answer.get("period_start")), _iso(answer.get("period_end"))
    return (start, end) if start and end and start <= end else None


def extract(
    text: str,
    provider: LlmProvider,
    *,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> Extraction:
    """Read the statement. Raises LlmUnavailable if the model cannot be reached and
    NothingFound if no transaction is found."""
    lines = text.splitlines()
    overview = "\n".join(
        lines[:HEAD_LINES] + (lines[-TAIL_LINES:] if len(lines) > HEAD_LINES else [])
    )
    answer = _ask(provider, STATEMENT_SYSTEM, f"Statement:\n{overview}", _statement_schema())
    accounts = _accounts(answer, text) or [Account(None, None, "bank", "USD", None, None)]
    extraction = Extraction(accounts=accounts, period=_period(answer))

    parts = chunks(text)
    progress(0, len(parts))
    known = ", ".join(a.account_last4 or "unknown" for a in accounts)
    period = (
        f"{extraction.period[0].isoformat()} to {extraction.period[1].isoformat()}"
        if extraction.period
        else "not printed"
    )
    for number, part in enumerate(parts, start=1):
        started = time.monotonic()
        prompt = f"Statement period: {period}\nAccounts (last 4): {known}\nText:\n{part}"
        found = _ask(provider, TRANSACTIONS_SYSTEM, prompt, _transactions_schema())
        _add_transactions(extraction, found.get("transactions"), part)
        logger.info(
            "extract chunk=%d/%d seconds=%.1f", number, len(parts), time.monotonic() - started
        )
        progress(number, len(parts))
    if not extraction.transactions:
        raise NothingFound("no transactions found")
    return extraction


def _add_transactions(extraction: Extraction, items: object, part: str) -> None:
    values = money_values(part)
    by_last4 = {a.account_last4: i for i, a in enumerate(extraction.accounts) if a.account_last4}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        when = _iso(item.get("date"))
        if when is None:
            extraction.rejected += 1
            continue
        account_index = by_last4.get(item.get("account_last4"), 0)
        account = extraction.accounts[account_index]
        minor = _amount(item.get("amount"), account.currency)
        if minor is None:
            extraction.rejected += 1
            continue
        in_period = extraction.period is None or (
            extraction.period[0] - PERIOD_SLACK <= when <= extraction.period[1] + PERIOD_SLACK
        )
        description = " ".join(str(item.get("description") or "").split()) or "(no description)"
        extraction.transactions.append(
            Transaction(
                account_index=account_index,
                date=when.isoformat(),
                description=description,
                amount_minor=minor if item.get("direction") == "in" else -minor,
                verified=minor in values and in_period,
            )
        )
