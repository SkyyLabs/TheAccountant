import pytest

from app.statements.dates import DateFormatError, parse_date


def test_us_format_reads_month_first():
    assert parse_date("03/04/2026", "MM/DD/YYYY") == "2026-03-04"


def test_indian_format_reads_day_first():
    assert parse_date("03/04/2026", "DD/MM/YYYY") == "2026-04-03"


@pytest.mark.parametrize(
    ("text", "date_format", "expected"),
    [
        ("03/04/26", "MM/DD/YY", "2026-03-04"),
        ("03/04/26", "DD/MM/YY", "2026-04-03"),
        ("03-04-2026", "DD-MM-YYYY", "2026-04-03"),
        ("03-04-26", "DD-MM-YY", "2026-04-03"),
        ("2026-03-04", "YYYY-MM-DD", "2026-03-04"),
        ("03 Apr 2026", "DD Mon YYYY", "2026-04-03"),
        ("03 APR 2026", "DD Mon YYYY", "2026-04-03"),
        ("03  Apr   2026", "DD Mon YYYY", "2026-04-03"),
        ("03-Apr-2026", "DD-Mon-YYYY", "2026-04-03"),
        ("03-apr-26", "DD-Mon-YY", "2026-04-03"),
        ("Mar 4, 2026", "Mon DD, YYYY", "2026-03-04"),
        ("3/4/2026", "MM/DD/YYYY", "2026-03-04"),
    ],
)
def test_declared_format_parses_to_iso(text, date_format, expected):
    assert parse_date(text, date_format) == expected


@pytest.mark.parametrize(
    ("text", "date_format"),
    [
        ("13/04/2026", "MM/DD/YYYY"),
        ("04/31/2026", "MM/DD/YYYY"),
        ("2026-03-04", "DD/MM/YYYY"),
        ("03/04/2026", "DD-MM-YYYY"),
        ("", "MM/DD/YYYY"),
    ],
)
def test_text_not_matching_the_declared_format_is_rejected(text, date_format):
    with pytest.raises(DateFormatError):
        parse_date(text, date_format)


def test_unknown_format_is_rejected():
    with pytest.raises(DateFormatError, match="unknown date format"):
        parse_date("03/04/2026", "auto")
