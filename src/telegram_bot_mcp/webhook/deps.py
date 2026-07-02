"""Shared request dependencies for the webhook routers."""

from fastapi import HTTPException, Request
from telegram.ext import Application


def require_application(request: Request) -> Application:
    """Return the initialized bot application or raise 503."""
    application: Application | None = getattr(request.app.state, "application", None)
    if application is None or application.bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    return application
