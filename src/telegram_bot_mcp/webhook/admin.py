"""Admin endpoints for managing the Telegram webhook registration."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from telegram.error import TelegramError

from ..config import load_config
from ..storage import utc_now_iso
from .deps import require_application

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


@router.post("/set_webhook")
async def set_webhook(
    request: Request, webhook_url: str, secret_token: str | None = None
) -> dict[str, Any]:
    """Register the webhook URL with Telegram."""
    application = require_application(request)

    secret = secret_token or load_config().telegram.webhook_secret
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="No webhook secret configured; set WEBHOOK_SECRET or pass secret_token",
        )

    try:
        await application.bot.set_webhook(url=webhook_url, secret_token=secret)
    except TelegramError as exc:
        logger.error("Error setting webhook: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "success",
        "message": f"Webhook set to: {webhook_url}",
        "timestamp": utc_now_iso(),
    }


@router.delete("/delete_webhook")
async def delete_webhook(request: Request) -> dict[str, Any]:
    """Remove the webhook registration."""
    application = require_application(request)

    try:
        await application.bot.delete_webhook()
    except TelegramError as exc:
        logger.error("Error deleting webhook: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "success",
        "message": "Webhook deleted",
        "timestamp": utc_now_iso(),
    }
