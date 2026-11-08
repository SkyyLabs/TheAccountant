"""Transaction fingerprints: the same transaction in two overlapping statements is stored
once, while genuine identical transactions within one statement are all kept."""

import hashlib
import json


def normalize_description(description: str) -> str:
    return " ".join(description.lower().split())


def fingerprinted(items: list[dict], account_id: int) -> list[dict]:
    """Each item has date, amount_minor, description, needs_review and raw (a dict). The
    occurrence number (identical rows earlier in this statement) keeps genuine repeats."""
    seen: dict[tuple, int] = {}
    rows = []
    for index, item in enumerate(items):
        normalized = normalize_description(item["description"])
        key = (item["date"], item["amount_minor"], normalized)
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        identity = f"{account_id}|{item['date']}|{item['amount_minor']}|{normalized}|{occurrence}"
        rows.append(
            {
                "row_index": index,
                "date": item["date"],
                "amount_minor": item["amount_minor"],
                "description": item["description"],
                "normalized_description": normalized,
                "raw_row": json.dumps(item["raw"], ensure_ascii=False),
                "fingerprint": hashlib.sha256(identity.encode()).hexdigest(),
                "needs_review": item["needs_review"],
            }
        )
    return rows
