from app.statements.extract import chunks, money_values


def test_money_values_are_read_as_positive_minor_units():
    assert money_values("Paid 1,250.00 and -42.10; balance 1,23,456.78") == {
        125000,
        4210,
        12345678,
    }


def test_numbers_without_two_decimals_are_not_money():
    assert money_values("Ref 27253852621 on 12/08, page 2") == set()


def test_long_text_is_split_at_line_ends():
    text = "\n".join(f"line {i:04d} " + "x" * 90 for i in range(100))

    parts = chunks(text)

    assert len(parts) > 1
    assert "\n".join(parts) == text
    assert all(len(part) <= 3600 for part in parts)


def test_blank_lines_are_dropped():
    assert chunks("a\n\n  \nb") == ["a\nb"]
