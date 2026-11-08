"""Finding the merchants a search term means ("coffee" -> the coffee shops), by embedding
similarity plus plain word matching. The mock provider's vectors stand in for the model."""

from conftest import account_answer, transaction_answer

from app import db
from app.chat.merchants import find_merchants

STATEMENT = (
    b"Example Bank 1111\n"
    b"03/04 SQ *BLUE BOTTLE COFFEE 0423 4.50\n03/05 PEETS COFFEE #12 3.75\n"
    b"03/06 SHELL OIL 5739 40.00\n03/07 NETFLIX.COM 15.49\n"
)


def import_merchants(upload) -> None:
    """Merchant keys: sq blue bottle coffee, peets coffee, shell oil, netflix com."""
    upload(
        STATEMENT,
        accounts=[account_answer(bank_name="Example Bank", last4="1111")],
        transactions=[
            transaction_answer("2026-03-04", "SQ *BLUE BOTTLE COFFEE 0423", "4.50", "out"),
            transaction_answer("2026-03-05", "PEETS COFFEE #12", "3.75", "out"),
            transaction_answer("2026-03-06", "SHELL OIL 5739", "40.00", "out"),
            transaction_answer("2026-03-07", "NETFLIX.COM", "15.49", "out"),
        ],
    )


def find(client, term: str) -> list[str]:
    connection = db.connect(client.app.state.settings.database_path)
    try:
        return find_merchants(connection, client.app.state.llm, term)
    finally:
        connection.close()


def test_merchants_close_in_meaning_to_the_term_are_found_best_first(client, upload):
    client.app.state.llm.vectors = {
        "cafe": [1.0, 0.0, 0.0],
        "peets coffee": [0.9, 0.3, 0.0],
        "sq blue bottle coffee": [1.0, 0.1, 0.0],
        "shell oil": [0.0, 1.0, 0.0],
    }
    import_merchants(upload)

    assert find(client, "cafe") == ["sq blue bottle coffee", "peets coffee"]


def test_merchants_far_below_the_best_match_are_left_out(client, upload):
    # cosine 1.0 for the best, 0.6 for the other: similar, but far below the best.
    client.app.state.llm.vectors = {
        "cafe": [1.0, 0.0, 0.0],
        "sq blue bottle coffee": [1.0, 0.0, 0.0],
        "peets coffee": [0.6, 0.8, 0.0],
    }
    import_merchants(upload)

    assert find(client, "cafe") == ["sq blue bottle coffee"]


def test_nothing_is_found_when_no_merchant_is_close_enough(client, upload):
    # cosine 0.3: the best match, but not similar enough.
    client.app.state.llm.vectors = {"gym": [0.3, 0.954, 0.0], "shell oil": [1.0, 0.0, 0.0]}
    import_merchants(upload)

    assert find(client, "gym") == []


def test_merchant_whose_name_has_the_term_as_a_word_is_found(client, upload):
    import_merchants(upload)

    assert find(client, "Netflix") == ["netflix com"]


def test_a_term_inside_a_longer_word_is_not_a_word_match(client, upload):
    import_merchants(upload)

    assert find(client, "net") == []


def test_merchants_are_embedded_once_after_import(client, upload):
    import_merchants(upload)
    after_import = sorted(client.app.state.llm.embedded)

    find(client, "coffee")
    find(client, "coffee")

    assert after_import == ["netflix com", "peets coffee", "shell oil", "sq blue bottle coffee"]
    assert client.app.state.llm.embedded.count("peets coffee") == 1


def test_changing_the_embedding_model_embeds_every_merchant_again(client, upload):
    import_merchants(upload)
    client.app.state.llm.embedding_model = "another-model"

    find(client, "coffee")

    assert client.app.state.llm.embedded.count("peets coffee") == 2
