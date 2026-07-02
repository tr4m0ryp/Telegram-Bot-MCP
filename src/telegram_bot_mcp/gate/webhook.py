"""Inbound Telegram webhook: the operator's Approve/Cancel tap.

This path never touches Claude. It verifies the tap came from the configured
operator, then approves-and-mints atomically: on Approve a one-time launch token
is minted, bound to the RoE hash snapshotted when the request was sent. The token
is never put in message text and never returned to Telegram — only "Approved" is
shown.
"""

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from telegram import Update
from telegram.error import TelegramError

from ..approval import APPROVE, cancel_pending, decode
from ..config import load_config
from ..tokens import approve_pending_and_mint
from .notify import get_bot

logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

router = APIRouter()


def _verify_secret(request: Request) -> None:
    """Enforce Telegram's secret header. Fails CLOSED if no secret is configured."""
    secret = load_config().telegram.webhook_secret
    if not secret:
        # Without a shared secret the request body (including from.id) is fully
        # attacker-controllable, so operator identity would be meaningless. Refuse.
        logger.error("WEBHOOK_SECRET not configured; refusing all webhook traffic")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    provided = request.headers.get(SECRET_HEADER, "")
    if not hmac.compare_digest(provided, secret):
        logger.warning("Webhook rejected: bad secret token")
        raise HTTPException(status_code=403, detail="Invalid secret token")


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, str]:
    """Handle a Telegram callback-query update from the operator."""
    _verify_secret(request)

    bot = await get_bot()
    update = Update.de_json(await request.json(), bot)
    query = update.callback_query if update else None
    if query is None:
        return {"status": "ignored"}

    operator_id = load_config().telegram.operator_user_id
    if operator_id is None:
        logger.error("OPERATOR_TELEGRAM_USER_ID not configured; refusing all taps")
        await query.answer(text="Not authorized.")
        return {"status": "unauthorized"}

    # Only the operator's taps are honored — even inside the same chat.
    if query.from_user is None or query.from_user.id != operator_id:
        logger.warning("Ignoring callback from non-operator user %s",
                       getattr(query.from_user, "id", "unknown"))
        await query.answer(text="Not authorized.")
        return {"status": "unauthorized"}

    data = decode(query.data or "")
    if data is None:
        await query.answer(text="Unrecognized action.")
        return {"status": "bad_data"}

    if data.decision == APPROVE:
        return await _approve(query, data.engagement_id, data.nonce)
    return await _cancel(query, data.engagement_id, data.nonce)


async def _approve(query, engagement_id: str, nonce: str) -> dict[str, str]:
    """Atomically approve + mint. The token value never leaves this function."""
    minted = await approve_pending_and_mint(engagement_id, nonce)
    if minted is None:
        await query.answer(text="This request already handled or expired.")
        await _edit(query, "Expired — no longer actionable.")
        return {"status": "stale"}
    await query.answer(text="Approved.")
    await _edit(query, "Approved — launch authorized.")
    return {"status": "approved"}


async def _cancel(query, engagement_id: str, nonce: str) -> dict[str, str]:
    matched = await cancel_pending(engagement_id, nonce)
    if not matched:
        await query.answer(text="This request already handled or expired.")
        await _edit(query, "Expired — no longer actionable.")
        return {"status": "stale"}
    await query.answer(text="Cancelled.")
    await _edit(query, "Cancelled — no token minted.")
    return {"status": "cancelled"}


async def _edit(query, text: str) -> None:
    """Replace the approval message's text and remove its buttons."""
    try:
        await query.edit_message_text(text=text)
    except TelegramError as exc:
        logger.warning("Could not edit approval message: %s", exc)
