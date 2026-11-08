"""Work out, from the statement alone, whose statement it is (bank, country, account type,
last 4 digits of the account) and how to read it (the column layout). No questions to the
user: the local LLM reads the first lines; code accepts only what it can check against the
file.

- The bank name must appear in the statement (or its file name).
- The last 4 digits must appear in the statement.
- The layout must parse every row (see layout.py, which also settles date format and sign).
Pattern heuristics stand in when the LLM is unavailable or wrong twice.

Amounts and dates still come only from the parsers; reconciliation checks the result.
"""

import logging
import re
from dataclasses import dataclass, replace

from app.llm.base import LlmError, LlmProvider, LlmUnavailable
from app.statements import layout

logger = logging.getLogger(__name__)

ATTEMPTS = 2
DEFAULT_DATE_FORMAT = {"US": "MM/DD/YYYY", "IN": "DD/MM/YYYY"}
CURRENCY = {"US": "USD", "IN": "INR"}

# Names a statement uses for the default banks, lower case.
BANK_ALIASES = {
    "chase": ("jpmorgan chase", "chase"),
    "discover": ("discover",),
    "capital_one": ("capital one", "capitalone"),
    "sofi": ("sofi",),
    "icici": ("icici",),
    "hdfc": ("hdfc",),
    "sbi": ("state bank of india", "sbi card", "sbi"),
    "axis": ("axis bank", "axis"),
}
CARD_WORDS = (
    "credit card",
    "card number",
    "minimum payment",
    "minimum amount due",
    "payment due date",
    "new balance",
    "credit limit",
)
BANK_ACCOUNT_WORDS = (
    "checking",
    "savings account",
    "savings a/c",
    "current account",
    "chase savings",
)
INDIA_WORDS = ("₹", " inr", "rs.", "upi", "neft", "imps", "ifsc", "india")
_MASKED_NUMBER = re.compile(r"(?:[x*•#]{2,}[\s-]?)+(\d{4})\b", re.IGNORECASE)
_LABELLED_NUMBER = re.compile(
    r"(?:a/c|acct|account|card)\s*(?:no\.?|number|#)?\s*[:\-]?\s*[\dx*•\s-]*?(\d{4})\b",
    re.IGNORECASE,
)

SYSTEM = """You read exports of bank and credit-card statements.
The user shows the statement as numbered lines; cells are separated by " | ".
Identify whose statement it is and how its transaction table is laid out. Rules:
- bank_name: the bank or card issuer exactly as written in the statement, or null.
- country: "US" or "IN" (India), from the bank, currency symbols and wording.
- account_type: "credit_card" for a card statement, otherwise "bank".
- account_last4: the last 4 digits of the account or card number as shown, or null.
- header_line is the line number of the column header row of the transaction table.
- Column names must be copied exactly from that header line.
- amount_mode: "signed" if one amount column where negative is money out, "inverted" if one
  amount column where positive is money out (common for credit-card exports), "debit_credit"
  if separate debit (money out) and credit (money in) columns.
- opening_balance_label and closing_balance_label are the exact words that introduce the
  statement's opening and closing balance (for cards: previous and new balance), or null.
Answer with JSON only."""


@dataclass(frozen=True)
class Identity:
    bank_name: str | None = None
    bank_id: str | None = None  # a known bank, when the name matched one
    country: str | None = None
    account_type: str | None = None
    account_last4: str | None = None


@dataclass(frozen=True)
class Understanding:
    identity: Identity
    mapping: dict | None  # complete and checked against every row, or None
    source: str  # "llm" or "heuristic"


def statement_text(rows: list[list[str]], filename: str = "") -> str:
    head = rows[: layout.HEAD_LINES]
    tail = rows[-layout.TAIL_LINES :] if len(rows) > layout.HEAD_LINES else []
    lines = [" ".join(cell for cell in row if cell) for row in [*head, *tail]]
    return f"{filename}\n" + "\n".join(lines)


def _known_bank(text: str, banks: dict[str, dict]) -> str | None:
    lowered = text.lower()
    for bank_id, aliases in BANK_ALIASES.items():
        # Letters-only boundaries: file names glue digits on ("Chase4410_Activity.csv").
        if bank_id in banks and any(
            re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", lowered) for a in aliases
        ):
            return bank_id
    for bank_id, bank in banks.items():
        if re.search(rf"\b{re.escape(bank['name'].lower())}\b", lowered):
            return bank_id
    return None


def heuristic_identity(text: str, banks: dict[str, dict]) -> Identity:
    lowered = text.lower()
    bank_id = _known_bank(text, banks)
    country = banks[bank_id]["country"] if bank_id else None
    if country is None:
        country = "IN" if any(word in lowered for word in INDIA_WORDS) else None
    filename = text.splitlines()[0] if text else ""
    # Exports often carry it only in the file name: "Chase4410_Activity20260301.CSV".
    match = (
        _MASKED_NUMBER.search(text)
        or _LABELLED_NUMBER.search(text)
        or re.search(r"[a-z](\d{4})(?!\d)", filename, re.IGNORECASE)
    )
    return Identity(
        bank_name=banks[bank_id]["name"] if bank_id else None,
        bank_id=bank_id,
        country=country,
        account_type=(
            "credit_card"
            if any(w in lowered for w in CARD_WORDS)
            else "bank"
            if any(w in lowered for w in BANK_ACCOUNT_WORDS)
            else None
        ),
        account_last4=match.group(1) if match else None,
    )


def _checked_identity(answer: dict, text: str, banks: dict[str, dict]) -> Identity:
    """Keep only what the statement itself confirms."""
    lowered = text.lower()
    name = answer.get("bank_name")
    name = name.strip() if isinstance(name, str) and name.strip() else None
    if name and name.lower() not in lowered:
        name = None  # not in the statement: the model made it up
    bank_id = _known_bank(name, banks) if name else None
    last4 = answer.get("account_last4")
    if not (isinstance(last4, str) and re.fullmatch(r"\d{4}", last4) and last4 in text):
        last4 = None
    country = answer.get("country") if answer.get("country") in CURRENCY else None
    account_type = answer.get("account_type")
    if account_type not in ("bank", "credit_card"):
        account_type = None
    return Identity(
        bank_name=banks[bank_id]["name"] if bank_id else name,
        bank_id=bank_id,
        country=banks[bank_id]["country"] if bank_id else country,
        account_type=account_type,
        account_last4=last4,
    )


def _merge(preferred: Identity, fallback: Identity) -> Identity:
    return Identity(
        bank_name=preferred.bank_name or fallback.bank_name,
        bank_id=preferred.bank_id or fallback.bank_id,
        country=preferred.country or fallback.country,
        account_type=preferred.account_type or fallback.account_type,
        account_last4=preferred.account_last4 or fallback.account_last4,
    )


def with_defaults(identity: Identity) -> Identity:
    return replace(
        identity,
        country=identity.country or "US",
        account_type=identity.account_type or "bank",
    )


def _schema() -> dict:
    schema = layout.schema()
    nullable_text = {"type": ["string", "null"]}
    schema["properties"] = {
        "bank_name": nullable_text,
        "country": {"enum": ["US", "IN"]},
        "account_type": {"enum": ["bank", "credit_card"]},
        "account_last4": nullable_text,
        **schema["properties"],
    }
    schema["required"] = ["bank_name", "country", "account_type", "account_last4"] + schema[
        "required"
    ]
    return schema


def understand(
    rows: list[list[str]],
    provider: LlmProvider,
    *,
    banks: dict[str, dict],
    filename: str = "",
) -> Understanding:
    text = statement_text(rows, filename)
    guessed = heuristic_identity(text, banks)
    prompt = layout.prompt(rows)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            answer = provider.complete_json(SYSTEM, prompt, _schema())
        except LlmUnavailable:
            logger.info("understand: llm unavailable, using heuristics")
            break
        except LlmError:
            answer = {}
        identity = with_defaults(_merge(_checked_identity(answer, text, banks), guessed))
        mapping = layout.finish_answer(
            answer,
            rows,
            account_type=identity.account_type,
            currency=CURRENCY[identity.country],
            default_date_format=_date_format(identity, banks),
        )
        if mapping is not None:
            logger.info("understand: llm accepted attempt=%d rows=%d", attempt, len(rows))
            return Understanding(identity, mapping, "llm")
        logger.info("understand: llm layout rejected attempt=%d", attempt)
    identity = with_defaults(guessed)
    mapping = layout.checked_heuristic_layout(
        rows,
        account_type=identity.account_type,
        currency=CURRENCY[identity.country],
        default_date_format=_date_format(identity, banks),
    )
    return Understanding(identity, mapping, "heuristic")


def _date_format(identity: Identity, banks: dict[str, dict]) -> str:
    if identity.bank_id:
        return banks[identity.bank_id]["default_date_format"]
    return DEFAULT_DATE_FORMAT[identity.country]


IDENTITY_SYSTEM = """You read the first page of a bank or credit-card statement.
- bank_name: the bank or card issuer exactly as written, or null.
- country: "US" or "IN" (India), from the bank, currency symbols and wording.
- account_type: "credit_card" for a card statement, otherwise "bank".
- account_last4: the last 4 digits of the account or card number as shown, or null.
Answer with JSON only."""


def identify(text: str, provider: LlmProvider, *, banks: dict[str, dict]) -> Identity:
    """Whose statement this is, for statements read line by line (no layout to propose).
    The LLM is asked only when the patterns miss the bank or the account type."""
    guessed = heuristic_identity(text, banks)
    if guessed.bank_id and guessed.account_type:
        return guessed
    schema = _schema()
    identity_fields = ["bank_name", "country", "account_type", "account_last4"]
    schema = {
        "type": "object",
        "properties": {k: schema["properties"][k] for k in identity_fields},
        "required": identity_fields,
    }
    question = "Statement:\n" + "\n".join(text.splitlines()[: layout.HEAD_LINES])
    try:
        answer = provider.complete_json(IDENTITY_SYSTEM, question, schema)
    except LlmUnavailable:
        return with_defaults(guessed)
    except LlmError:
        answer = {}
    return with_defaults(_merge(_checked_identity(answer, text, banks), guessed))
