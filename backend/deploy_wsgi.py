"""Hosted entry point: Flask API and compiled React UI on the same origin."""

from pathlib import Path

from app import app, startup_actions
from frontend_static import configure_frontend


configure_frontend(app, Path(__file__).resolve().parents[1] / "frontend" / "dist")
startup_actions()
