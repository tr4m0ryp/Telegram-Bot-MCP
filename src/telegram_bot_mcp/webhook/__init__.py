"""Production webhook server (FastAPI) for the Telegram bot."""

from .app import app, create_app

__all__ = ["app", "create_app"]
