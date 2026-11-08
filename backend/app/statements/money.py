"""Parse amount text from a statement into integer minor units (cents, paise). Never floats.

The sign returned is the sign the text itself carries (minus, parentheses, Dr/Cr). Turning a
card "charge" column into money out is the bank profile's job, not this module's.
"""

import re
from decimal import Decimal

MINOR_UNIT_DIGITS = {"USD": 2, "INR": 2}

# Optional sign, currency marker, sign again (for "$-12.50"), number, trailing sign, trailing code.
_AMOUNT = re.compile(
    r"^(?P<lead>[-+−])?\s*(?:\$|₹|rs\.?|inr|usd)?\s*(?P<inner>[-−])?\s*"
    r"(?P<number>[\d,]+(?:\.\d+)?)\s*(?P<trail>-)?\s*(?:inr|usd)?$",
    re.IGNORECASE,
)
# Plain digits, Western grouping (1,234,567) or Indian grouping (12,34,567).
_GROUPED = re.compile(r"^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d+)?$")
_DR_CR = re.compile(r"\s*(?<![a-z])(?P<marker>dr|cr)\.?$", re.IGNORECASE)
_PARENTHESES = re.compile(r"^\((?P<inner>.*)\)$")


class AmountError(ValueError):
    pass


def parse_amount(text: str, currency: str) -> int:
    if currency not in MINOR_UNIT_DIGITS:
        raise AmountError(f"unsupported currency {currency!r}")
    digits = MINOR_UNIT_DIGITS[currency]
    remaining = text.strip()
    negative_markers = 0
    sign_markers = 0

    dr_cr = _DR_CR.search(remaining)
    if dr_cr:
        sign_markers += 1
        negative_markers += dr_cr["marker"].lower() == "dr"
        remaining = remaining[: dr_cr.start()].strip()

    parentheses = _PARENTHESES.match(remaining)
    if parentheses:
        sign_markers += 1
        negative_markers += 1
        remaining = parentheses["inner"].strip()

    match = _AMOUNT.match(remaining)
    if not match or not _GROUPED.match(match["number"]):
        raise AmountError(f"not an amount: {text!r}")
    for group in ("lead", "inner", "trail"):
        if match[group]:
            sign_markers += 1
            negative_markers += match[group] != "+"
    if sign_markers > 1:
        raise AmountError(f"conflicting sign markers: {text!r}")

    number = match["number"].replace(",", "")
    if len(number.partition(".")[2]) > digits:
        raise AmountError(f"more than {digits} decimal places: {text!r}")
    minor = int(Decimal(number).scaleb(digits))
    return -minor if negative_markers else minor
