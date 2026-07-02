"""Telegram webhook ingestion: receive updates and dispatch them to the bot."""

import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application

logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

router = APIRouter()


async def process_update(application: Application, update: Update) -> None:
    """Run an update through the application; handler errors go to the error handler."""
    await application.process_update(update)
    if update.message:
        user_id = update.message.from_user.id if update.message.from_user else "unknown"
        text = update.message.text or "non-text message"
        logger.info("Processed message from user %s: %.50s", user_id, text)


@router.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    """Handle a Telegram webhook update, rejecting requests without the shared secret."""
    application: Application = request.app.state.application
    secret: str | None = getattr(request.app.state, "webhook_secret", None)

    if secret is not None:
        provided = request.headers.get(SECRET_HEADER, "")
        if not hmac.compare_digest(provided, secret):
            logger.warning("Webhook rejected: missing or invalid secret token")
            raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        update_data = await request.json()
    except json.JSONDecodeError as exc:
        logger.warning("Webhook received invalid JSON: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    update = Update.de_json(update_data, application.bot)
    if update is None:
        logger.warning("Received invalid update data")
        return JSONResponse(
            content={"status": "error", "message": "Invalid update"},
            status_code=400,
        )

    background_tasks.add_task(process_update, application, update)
    return JSONResponse(content={"status": "ok", "message": "Update received"})
