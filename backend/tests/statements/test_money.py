import pytest

from app.statements.money import AmountError, parse_amount


@pytest.mark.parametrize(
    ("text", "currency", "expected_minor"),
    [
        ("12.50", "USD", 1250),
        ("1,234.56", "USD", 123456),
        ("1,234,567.89", "USD", 123456789),
        ("$42.10", "USD", 4210),
        ("-$42.10", "USD", -4210),
        ("$-42.10", "USD", -4210),
        ("(42.10)", "USD", -4210),
        ("($1,000.00)", "USD", -100000),
        ("42.10-", "USD", -4210),
        ("+42.10", "USD", 4210),
        ("7", "USD", 700),
        ("7.5", "USD", 750),
        ("0.00", "USD", 0),
        ("1,23,456.78", "INR", 12345678),
        ("12,34,56,789.00", "INR", 12345678900),
        ("1,23,456.78 Dr", "INR", -12345678),
        ("1,23,456.78 Cr", "INR", 12345678),
        ("500.00DR", "INR", -50000),
        ("500.00 cr.", "INR", 50000),
        ("₹2,500.00", "INR", 250000),
        ("Rs. 2,500.00", "INR", 250000),
        ("INR 2,500.00", "INR", 250000),
        ("2,500.00 INR", "INR", 250000),
        ("−2,500.00", "INR", -250000),
        ("  99.99  ", "USD", 9999),
    ],
)
def test_amount_text_parses_to_signed_minor_units(text, currency, expected_minor):
    assert parse_amount(text, currency) == expected_minor


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "12.345",
        "1,2345.00",
        "12,34.00",
        "1.2.3",
        "-(42.10)",
        "-42.10 Dr",
        "(42.10) Cr",
        "--42.10",
    ],
)
def test_malformed_or_ambiguous_amount_is_rejected(text):
    with pytest.raises(AmountError):
        parse_amount(text, "USD")


def test_unsupported_currency_is_rejected():
    with pytest.raises(AmountError, match="unsupported currency"):
        parse_amount("10.00", "EUR")


def test_result_is_an_int_not_a_float():
    assert type(parse_amount("0.10", "USD")) is int
