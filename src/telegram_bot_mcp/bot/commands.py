"""Command handlers: /start, /help, /info, /stats, /clear."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..storage import UserSession, store
from . import replies

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user and send the welcome message."""
    user = update.effective_user
    if update.message is None or user is None or update.effective_chat is None:
        return

    store.record_session(
        UserSession(
            user_id=user.id,
            chat_id=update.effective_chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    )
    await update.message.reply_text(replies.welcome(user.first_name), parse_mode="HTML")
    store.log_interaction(user.id, "command", "/start", "Welcome message sent")


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the help text."""
    user = update.effective_user
    if update.message is None or user is None:
        return

    await update.message.reply_text(replies.help_text(), parse_mode="HTML")
    store.log_interaction(user.id, "command", "/help", "Help information provided")


async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the user's profile and session information."""
    user = update.effective_user
    if update.message is None or user is None or update.effective_chat is None:
        return

    session = store.sessions.get(user.id)
    activity = store.recent_user_activity(user.id)
    text = replies.info_text(user, session, update.effective_chat, activity)
    await update.message.reply_text(text, parse_mode="HTML")
    store.log_interaction(user.id, "command", "/info", "User info provided")


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send global bot statistics."""
    user = update.effective_user
    if update.message is None or user is None:
        return

    text = replies.stats_text(
        total_users=len(store.sessions),
        total_interactions=len(store.interactions),
        most_active_user=store.most_active_user(),
        command_counts=store.command_counts(),
        last_interaction=store.interactions[-1].timestamp if store.interactions else None,
    )
    await update.message.reply_text(text, parse_mode="HTML")
    store.log_interaction(user.id, "command", "/stats", "Stats provided")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the user's conversation history and message count."""
    user = update.effective_user
    if update.message is None or user is None:
        return

    store.clear_user(user.id)
    await update.message.reply_text(replies.CLEAR_CONFIRMATION, parse_mode="HTML")
    store.log_interaction(user.id, "command", "/clear", "History cleared")
