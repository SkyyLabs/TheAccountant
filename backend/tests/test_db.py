from concurrent.futures import ThreadPoolExecutor

from app import db


def test_a_connection_opened_in_one_thread_can_be_used_in_another(tmp_path):
    # FastAPI may open a request's connection (sync dependency) on one worker thread and
    # run the endpoint on another, so the connection must survive the handoff.
    connection = db.connect(tmp_path / "app.db")

    with ThreadPoolExecutor(max_workers=1) as other_thread:
        answer = other_thread.submit(lambda: connection.execute("SELECT 42").fetchone()[0])

    assert answer.result() == 42
