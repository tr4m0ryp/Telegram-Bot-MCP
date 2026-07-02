"""Inbound Telegram webhook: the operator's Approve/Cancel tap.

This path never touches Claude. It verifies the tap came from the configured
operator, matches it to a pending approval, and on Approve mints a one-time
launch token bound to the engagement's signed RoE hash. The token is never put
in message text and never returned to Telegram — only "Approved" is shown.
"""

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from telegram import Update
from telegram.error import TelegramError

from ..approval import APPROVE, decode, resolve_pending
from ..config import load_config
from ..tokens import lookup_roe_hash, mint_token
from .notify import get_bot

logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

router = APIRouter()


def _verify_secret(request: Request) -> None:
    secret = load_config().telegram.webhook_secret
    if secret is None:
        return
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
        # Not a button tap (e.g. a plain message). Nothing to do.
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

    decision = "approved" if data.decision == APPROVE else "cancelled"
    matched = await resolve_pending(data.engagement_id, data.nonce, decision)
    if not matched:
        await query.answer(text="This request already handled or expired.")
        await _edit(query, "Expired — no longer actionable.")
        return {"status": "stale"}

    if decision == "cancelled":
        await query.answer(text="Cancelled.")
        await _edit(query, "Cancelled — no token minted.")
        return {"status": "cancelled"}

    return await _approve(query, data.engagement_id)


async def _approve(query, engagement_id: str) -> dict[str, str]:
    """Mint a token bound to the engagement's RoE hash. Token never leaves here."""
    roe_hash = await lookup_roe_hash(engagement_id)
    if roe_hash is None:
        logger.error("No RoE hash for engagement %s; cannot mint", engagement_id)
        await query.answer(text="No signed scope on file — cannot authorize.")
        await _edit(query, "Approval failed — no signed scope on file.")
        return {"status": "no_roe"}

    await mint_token(engagement_id, roe_hash)  # stored; value intentionally unused here
    await query.answer(text="Approved.")
    await _edit(query, "Approved — launch authorized.")
    return {"status": "approved"}


async def _edit(query, text: str) -> None:
    """Replace the approval message's text and remove its buttons."""
    try:
        await query.edit_message_text(text=text)
    except TelegramError as exc:
        logger.warning("Could not edit approval message: %s", exc)
