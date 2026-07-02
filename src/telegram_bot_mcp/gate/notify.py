"""Outbound Telegram: shared bot client and the message senders.

The bot client is shared with the webhook handler (one process), so an approval
request sent here and the operator's tap handled there see the same bot.
"""

import asyncio
import logging
from html import escape

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from ..approval import APPROVE, CANCEL, CallbackData
from ..config import load_config

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_bot_lock = asyncio.Lock()


async def get_bot() -> Bot:
    """Return the shared Bot client, creating and initializing it on first use."""
    global _bot
    if _bot is None:
        async with _bot_lock:
            if _bot is None:
                bot = Bot(token=load_config().telegram.bot_token)
                await bot.initialize()
                _bot = bot
                logger.info("Telegram bot client initialized")
    return _bot


async def close_bot() -> None:
    """Shut down the shared bot client, releasing its HTTP connections."""
    global _bot
    if _bot is not None:
        await _bot.shutdown()
        _bot = None


def _require_operator_chat() -> int:
    chat_id = load_config().telegram.operator_chat_id
    if chat_id is None:
        raise ValueError("OPERATOR_CHAT_ID is not configured")
    return chat_id


async def send_notification(text: str) -> int:
    """Send a plain notification to the operator chat. Returns the message id."""
    bot = await get_bot()
    message = await bot.send_message(chat_id=_require_operator_chat(), text=text)
    return message.message_id


def _approval_text(
    engagement_id: str,
    signed_company: str,
    signed_hosts: list[str],
    requested_company: str,
    requested_hosts: list[str],
) -> str:
    """Message body. Shows the SIGNED scope; flags any routine/​signed mismatch."""
    hosts = "\n".join(f"  - {escape(host)}" for host in signed_hosts) or "  (none listed)"
    body = (
        "<b>Launch approval requested</b>\n\n"
        f"Engagement: <code>{escape(engagement_id)}</code>\n"
        f"Company (signed): {escape(signed_company)}\n\n"
        f"<b>Signed scope</b> ({len(signed_hosts)} host(s)):\n{hosts}\n\n"
    )
    mismatch = requested_company != signed_company or sorted(requested_hosts) != sorted(
        signed_hosts
    )
    if mismatch:
        body += (
            "<b>Note:</b> the routine requested a scope that differs from the signed "
            "record above. Only the signed scope will be authorized.\n\n"
        )
    body += "Approve authorizes a black-box run against the signed scope above."
    return body


def _approval_keyboard(engagement_id: str, nonce: str) -> InlineKeyboardMarkup:
    approve = CallbackData(APPROVE, engagement_id, nonce).encode()
    cancel = CallbackData(CANCEL, engagement_id, nonce).encode()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=approve),
                InlineKeyboardButton("Cancel", callback_data=cancel),
            ]
        ]
    )


async def send_approval_request(
    engagement_id: str,
    nonce: str,
    signed_company: str,
    signed_hosts: list[str],
    requested_company: str,
    requested_hosts: list[str],
) -> tuple[int, int]:
    """Send the signed scope + Approve/Cancel buttons. Returns (chat_id, message_id)."""
    bot = await get_bot()
    chat_id = _require_operator_chat()
    message = await bot.send_message(
        chat_id=chat_id,
        text=_approval_text(
            engagement_id, signed_company, signed_hosts, requested_company, requested_hosts
        ),
        parse_mode="HTML",
        reply_markup=_approval_keyboard(engagement_id, nonce),
    )
    return chat_id, message.message_id
