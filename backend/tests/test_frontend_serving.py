import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def frontend_client(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app shell</html>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside dist")
    with TestClient(create_app(settings, frontend_dist=dist)) as test_client:
        yield test_client


def test_root_serves_the_app_shell(frontend_client):
    response = frontend_client.get("/")

    assert response.status_code == 200
    assert response.text == "<html>app shell</html>"


def test_client_side_route_on_reload_serves_the_app_shell(frontend_client):
    response = frontend_client.get("/statements")

    assert response.status_code == 200
    assert response.text == "<html>app shell</html>"


def test_built_asset_is_served_as_a_file(frontend_client):
    response = frontend_client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('app')"


def test_unknown_api_route_still_returns_json_error_not_the_shell(frontend_client):
    response = frontend_client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_api_routes_take_precedence_over_the_shell(frontend_client):
    assert frontend_client.get("/api/health").json()["status"] == "ok"


def test_path_traversal_outside_dist_serves_the_shell_not_the_file(frontend_client):
    response = frontend_client.get("/..%2Fsecret.txt")

    assert "outside dist" not in response.text
