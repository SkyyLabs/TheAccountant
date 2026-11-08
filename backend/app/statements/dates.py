"""Parse statement dates with the format the bank or account declares. Never guessed per row:
03/04/2026 is valid as both MM/DD and DD/MM, and a wrong guess silently swaps day and month.
"""

from datetime import datetime

# Display name (stored on banks and accounts) to strptime pattern. %b matches month
# abbreviations case-insensitively, so "MAR" and "Mar" both parse.
FORMATS = {
    "MM/DD/YYYY": "%m/%d/%Y",
    "MM/DD/YY": "%m/%d/%y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD/MM/YY": "%d/%m/%y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "DD-MM-YY": "%d-%m-%y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD Mon YYYY": "%d %b %Y",
    "DD-Mon-YYYY": "%d-%b-%Y",
    "DD-Mon-YY": "%d-%b-%y",
    "Mon DD, YYYY": "%b %d, %Y",
}


class DateFormatError(ValueError):
    pass


def parse_date(text: str, date_format: str) -> str:
    """Return the date as ISO YYYY-MM-DD."""
    if date_format not in FORMATS:
        raise DateFormatError(f"unknown date format {date_format!r}")
    normalized = " ".join(text.split())
    try:
        return datetime.strptime(normalized, FORMATS[date_format]).date().isoformat()
    except ValueError:
        raise DateFormatError(f"{text!r} does not match {date_format}") from None
