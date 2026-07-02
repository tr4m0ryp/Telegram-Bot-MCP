"""Outbound Telegram: shared bot client and the message senders.

The bot client is shared with the webhook handler (one process), so an approval
request sent here and the operator's tap handled there see the same bot.
"""

import logging
from html import escape

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from ..approval import APPROVE, CANCEL, CallbackData
from ..config import load_config

logger = logging.getLogger(__name__)

_bot: Bot | None = None


async def get_bot() -> Bot:
    """Return the shared Bot client, creating and initializing it on first use."""
    global _bot
    if _bot is None:
        bot = Bot(token=load_config().telegram.bot_token)
        await bot.initialize()
        _bot = bot
        logger.info("Telegram bot client initialized")
    return _bot


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


def _approval_text(company_name: str, scope_hosts: list[str], engagement_id: str) -> str:
    hosts = "\n".join(f"  - {escape(host)}" for host in scope_hosts) or "  (none listed)"
    return (
        "<b>Launch approval requested</b>\n\n"
        f"Engagement: <code>{escape(engagement_id)}</code>\n"
        f"Company: {escape(company_name)}\n\n"
        f"<b>Scope</b> ({len(scope_hosts)} host(s)):\n{hosts}\n\n"
        "Approve authorizes a black-box run against the scope above."
    )


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
    engagement_id: str, company_name: str, scope_hosts: list[str], nonce: str
) -> tuple[int, int]:
    """Send the scope + Approve/Cancel buttons. Returns (chat_id, message_id)."""
    bot = await get_bot()
    chat_id = _require_operator_chat()
    message = await bot.send_message(
        chat_id=chat_id,
        text=_approval_text(company_name, scope_hosts, engagement_id),
        parse_mode="HTML",
        reply_markup=_approval_keyboard(engagement_id, nonce),
    )
    return chat_id, message.message_id
