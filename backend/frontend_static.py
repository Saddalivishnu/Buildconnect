"""Serve the compiled React application alongside the Flask API."""

from pathlib import Path

from flask import abort, jsonify, send_from_directory


def configure_frontend(app, dist_dir):
    """Register SPA routes without changing development API startup behavior."""
    root = Path(dist_dir).resolve()
    index = root / "index.html"
    if not index.is_file() or not index.resolve().is_relative_to(root):
        raise RuntimeError(
            "The compiled frontend is missing. Run npm ci and npm run build "
            "from the frontend directory before starting the deployment."
        )

    def serve_frontend(path):
        # Missing API routes must never silently return the SPA's HTML.
        if path == "api" or path.startswith("api/"):
            return jsonify({"error": "Resource not found."}), 404

        # Resolve symlinks as well as URL traversal before accessing any file.
        relative = Path(path)
        if "\\" in path or any(part.startswith(".") for part in relative.parts):
            abort(404)
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            abort(404)
        if path and target.is_file():
            return send_from_directory(root, path)

        # Missing JS/CSS/assets must return 404 instead of HTML with a 200 status.
        if path == "assets" or path.startswith("assets/") or relative.suffix:
            abort(404)
        return send_from_directory(root, "index.html", max_age=0)

    app.add_url_rule(
        "/", endpoint="frontend_index", defaults={"path": ""}, view_func=serve_frontend
    )
    app.add_url_rule(
        "/<path:path>", endpoint="frontend_route", view_func=serve_frontend
    )
