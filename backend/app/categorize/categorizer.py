"""Categorize transactions: user rules first, then the stored result for the same merchant,
then the local LLM in batches, constrained to the category list. Low-confidence or invalid
LLM output becomes Uncategorized and needs review. Every decision is a new assignment row."""

import logging
import re
import sqlite3
import time

from app import db
from app.llm.base import LlmError, LlmProvider, LlmUnavailable

logger = logging.getLogger(__name__)

UNCATEGORIZED = "Uncategorized"
BATCH_SIZE = 20
ATTEMPTS = 2
MIN_CONFIDENCE = 0.6

SYSTEM = """You categorize personal bank and credit-card transactions.
For each transaction pick exactly one category from the allowed list. Use the description
and whether money went out or came in. If no category fits or you are unsure, choose
"Uncategorized" and a low confidence. Confidence is between 0 and 1.
Categories that are easy to confuse:
- Card Payments: paying a credit card bill ("payment to card", "autopay", "payment thank you",
  "e-payment" to a card issuer). Not income, even when money comes in on the card.
- Transfers: money moved between the person's own accounts or wallets (online transfer,
  to/from savings, Venmo or PayPal cash-out, IMPS/NEFT to self).
- Groceries: supermarkets and grocery delivery (BigBasket, Instacart, Whole Foods).
- Dining: restaurants, cafes and cooked-food delivery (Swiggy, Zomato, DoorDash, Uber Eats).
- Subscriptions: recurring digital services (streaming, music, software, Prime).
Answer with JSON only."""


def merchant_key(description: str) -> str:
    """Lower-case words without digits or punctuation: reference numbers differ per
    transaction, the merchant does not."""
    words = re.split(r"[^a-z0-9]+", description.lower())
    return " ".join(word for word in words if word and not any(c.isdigit() for c in word))


def rule_matches(rule: sqlite3.Row, key: str, amount_minor: int) -> bool:
    if rule["match_type"] == "exact" and key != rule["pattern"]:
        return False
    if rule["match_type"] == "contains" and rule["pattern"] not in key:
        return False
    if rule["amount_min_minor"] is not None and amount_minor < rule["amount_min_minor"]:
        return False
    return rule["amount_max_minor"] is None or amount_minor <= rule["amount_max_minor"]


def first_matching_rule(rules: list[sqlite3.Row], key: str, amount_minor: int):
    return next((rule for rule in rules if rule_matches(rule, key, amount_minor)), None)


def categorize(
    connection: sqlite3.Connection, provider: LlmProvider, statement_id: int | None = None
) -> str:
    """Categorize every transaction without a category (of one statement, or all).
    Returns "done", or "llm_unavailable" when some were left for a later run."""
    pending = db.uncategorized_transactions(connection, statement_id)
    keys = {row["id"]: merchant_key(row["description"]) for row in pending}
    db.set_merchant_keys(connection, list(keys.items()))
    rules = db.list_rules(connection)
    assignments: list[tuple[int, int, str, bool]] = []
    for_llm = []
    for row in pending:
        rule = first_matching_rule(rules, keys[row["id"]], row["amount_minor"])
        if rule is not None:
            assignments.append((row["id"], rule["category_id"], "rule", False))
            continue
        stored = db.stored_category_for_merchant(connection, keys[row["id"]])
        if stored is not None:
            assignments.append((row["id"], stored, "cache", False))
            continue
        for_llm.append(row)
    db.add_category_assignments(connection, assignments)

    status = "done"
    if for_llm:
        try:
            db.add_category_assignments(connection, _ask_llm(connection, provider, for_llm, keys))
        except LlmUnavailable:
            logger.info("categorize: llm unavailable, %d left pending", len(for_llm))
            status = "llm_unavailable"
    statement_ids = sorted({row["statement_id"] for row in pending})
    if statement_id is not None:
        statement_ids = [statement_id]
    db.set_categorization_status(connection, statement_ids, status)
    logger.info(
        "categorize: transactions=%d by_rule_or_cache=%d by_llm=%d status=%s",
        len(pending),
        len(assignments),
        len(for_llm),
        status,
    )
    return status


def _ask_llm(connection, provider, rows, keys) -> list[tuple[int, int, str, bool]]:
    """One question per merchant, direction and account type; the answer applies to all its
    transactions."""
    categories = {row["name"]: row for row in db.list_categories(connection)}
    uncategorized_id = categories[UNCATEGORIZED]["id"]
    groups: dict[tuple, list] = {}
    for row in rows:
        group = (keys[row["id"]], row["amount_minor"] < 0, row["country"], row["account_type"])
        groups.setdefault(group, []).append(row)
    items = list(groups.items())
    assignments = []
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        country = batch[0][0][2]
        allowed = [name for name, c in categories.items() if c["region"] in ("both", country)]
        answers = _ask_batch(provider, batch, allowed)
        for index, (_group, members) in enumerate(batch):
            category_name, confidence = answers.get(index, (UNCATEGORIZED, 0.0))
            confident = category_name != UNCATEGORIZED and confidence >= MIN_CONFIDENCE
            category_id = categories[category_name]["id"] if confident else uncategorized_id
            for row in members:
                assignments.append((row["id"], category_id, "llm", not confident))
    return assignments


def _ask_batch(provider, batch, allowed: list[str]) -> dict[int, tuple[str, float]]:
    lines = []
    for index, ((_key, money_out, _country, account_type), members) in enumerate(batch):
        example = members[0]
        direction = "money out" if money_out else "money in"
        # Money in on a card is almost always a bill payment; on a bank account it is not.
        on = "a credit card" if account_type == "credit_card" else "a bank account"
        lines.append(
            f'{index}: "{example["description"]}" ({direction} on {on}, {example["currency"]})'
        )
    prompt = f"Allowed categories: {', '.join(allowed)}\nTransactions:\n" + "\n".join(lines)
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "category": {"enum": allowed},
                        "confidence": {"type": "number"},
                    },
                    "required": ["index", "category", "confidence"],
                },
            }
        },
        "required": ["items"],
    }
    answers: dict[int, tuple[str, float]] = {}
    for attempt in range(1, ATTEMPTS + 1):
        started = time.monotonic()
        try:
            answer = provider.complete_json(SYSTEM, prompt, schema)
        except LlmUnavailable:
            raise
        except LlmError:
            answer = {}
        for item in answer.get("items", []) if isinstance(answer.get("items"), list) else []:
            if not isinstance(item, dict):
                continue
            index, category, confidence = (
                item.get("index"),
                item.get("category"),
                item.get("confidence"),
            )
            valid = (
                isinstance(index, int)
                and 0 <= index < len(batch)
                and category in allowed
                and isinstance(confidence, int | float)
            )
            if valid and index not in answers:
                answers[index] = (category, float(confidence))
        logger.info(
            "categorize batch attempt=%d size=%d answered=%d seconds=%.1f",
            attempt,
            len(batch),
            len(answers),
            time.monotonic() - started,
        )
        if len(answers) == len(batch):
            break
    return answers
