"""Deployment routing checks without importing the application or its database."""

from flask import Flask, jsonify
import pytest

from frontend_static import configure_frontend


@pytest.fixture
def frontend_client(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>BuildConnect preview</title>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app-test.js").write_text("console.log('BuildConnect');")
    outside = tmp_path / "outside.txt"
    outside.write_text("must not be exposed")
    (assets / "outside.txt").symlink_to(outside)

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    configure_frontend(app, dist)
    return app.test_client()


@pytest.mark.parametrize("path", ["/", "/procurement", "/projects/123"])
def test_spa_root_and_client_routes(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"BuildConnect preview" in response.data
    assert "max-age=0" in response.headers["Cache-Control"]


def test_existing_api_route_is_preserved(frontend_client):
    response = frontend_client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api", "/api/unknown", "/api/unknown/nested"])
def test_unknown_api_routes_return_json_not_html(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 404
    assert response.get_json() == {"error": "Resource not found."}


def test_compiled_asset_is_served(frontend_client):
    response = frontend_client.get("/assets/app-test.js")
    assert response.status_code == 200
    assert response.mimetype in {"text/javascript", "application/javascript"}
    assert response.data == b"console.log('BuildConnect');"


@pytest.mark.parametrize("path", ["/assets", "/assets/missing.js", "/favicon.ico"])
def test_missing_assets_do_not_return_spa(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 404
    assert b"BuildConnect preview" not in response.data


@pytest.mark.parametrize(
    "path",
    ["/%2e%2e/outside.txt", "/assets/%2e%2e/%2e%2e/outside.txt",
     "/assets/outside.txt", "/%5c..%5coutside.txt", "/.env"],
)
def test_traversal_and_symlink_escape_are_rejected(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 404
    assert b"must not be exposed" not in response.data


def test_missing_build_fails_before_routes_are_registered(tmp_path):
    app = Flask(__name__)
    with pytest.raises(RuntimeError, match="compiled frontend is missing"):
        configure_frontend(app, tmp_path / "missing-dist")
    assert "frontend_index" not in app.view_functions
