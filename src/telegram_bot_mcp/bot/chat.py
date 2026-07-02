"""Free-text message handling and contextual replies."""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from ..storage import UserSession, store
from . import replies

logger = logging.getLogger(__name__)

_GREETING = re.compile(r"\b(hello|hi|hey)\b", re.IGNORECASE)


def contextual_reply(text: str, message_count: int) -> str:
    """Build a reply that reflects the user's conversation so far."""
    if message_count <= 1:
        return f"Welcome! This is your first message. You said: {text}"
    if _GREETING.search(text):
        return f"Hello again! You have sent {message_count} messages so far. How can I help?"
    if "?" in text:
        return (
            f"Good question. Considering '{text}' in the context of our previous "
            f"{message_count - 1} messages."
        )
    return f"Noted: '{text}'. Reply is based on your {message_count}-message history."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle an incoming text message: log it and reply in context."""
    user = update.effective_user
    message = update.message
    if message is None or user is None or message.text is None or update.effective_chat is None:
        return

    session = store.touch_session(user.id)
    if session is None:
        # First contact without /start: register the user so stats and
        # broadcasts include them, and count this message.
        session = UserSession(
            user_id=user.id,
            chat_id=update.effective_chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            message_count=1,
        )
        store.record_session(session)

    store.log_interaction(user.id, "message", message.text)

    response = replies.message_reply(
        message.text, contextual_reply(message.text, session.message_count)
    )
    await message.reply_text(response, parse_mode="HTML")
    store.log_interaction(user.id, "bot_response", response, "Response sent")
