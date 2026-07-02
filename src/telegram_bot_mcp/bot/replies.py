"""User-facing reply templates, kept apart from handler logic.

All user-derived text is passed through html.escape before being placed in an
HTML-parsed reply, so messages or names containing '<', '>', or '&' cannot break
Telegram's entity parsing (which would otherwise reject the whole reply).
"""

from html import escape

from telegram import Chat, User

from ..storage import Interaction, UserSession

# Single source for the command list rendered in both /start and /help.
COMMANDS: tuple[tuple[str, str], ...] = (
    ("/start", "Show the welcome message"),
    ("/help", "Get detailed help information"),
    ("/info", "Show your user information"),
    ("/stats", "View bot statistics"),
    ("/clear", "Clear your conversation history"),
)


def _command_lines() -> str:
    return "\n".join(f"{command} - {description}" for command, description in COMMANDS)


def welcome(first_name: str | None) -> str:
    return (
        "<b>Welcome to the Telegram Bot MCP!</b>\n\n"
        f"Hello {escape(first_name or 'there')}. This bot is powered by the Model Context "
        "Protocol (MCP).\n\n"
        f"<b>Commands:</b>\n{_command_lines()}\n\n"
        "Send any message and the bot will respond."
    )


def help_text() -> str:
    return (
        "<b>Bot Help</b>\n\n"
        f"<b>Commands:</b>\n{_command_lines()}\n\n"
        "<b>Features:</b>\n"
        "- Context-aware message processing\n"
        "- Message tracking and user statistics\n"
        "- MCP integration for AI interactions\n\n"
        "Send any text message and the bot will process it with your conversation context."
    )


CLEAR_CONFIRMATION = (
    "<b>History cleared</b>\n\n"
    "Your conversation history has been cleared. This affects your personal message "
    "history, the context for future conversations, and your message count statistics. "
    "Your profile information remains unchanged."
)


def info_text(
    user: User,
    session: UserSession | None,
    chat: Chat,
    activity: list[Interaction],
) -> str:
    if activity:
        activity_lines = "\n".join(
            f"- {entry.timestamp[:19]}: {escape(entry.type)} - {escape(entry.content[:50])}"
            for entry in activity
        )
    else:
        activity_lines = "No recent activity"

    full_name = escape(f"{user.first_name or ''} {user.last_name or ''}".strip())
    return (
        "<b>Your Information</b>\n\n"
        "<b>Telegram profile:</b>\n"
        f"- User ID: <code>{user.id}</code>\n"
        f"- Username: @{escape(user.username or 'Not set')}\n"
        f"- Name: {full_name or 'Not set'}\n"
        f"- Language: {escape(user.language_code or 'Not detected')}\n\n"
        "<b>Session:</b>\n"
        f"- Last seen: {session.last_seen if session else 'Unknown'}\n"
        f"- Messages sent: {session.message_count if session else 0}\n"
        f"- Chat ID: <code>{chat.id}</code>\n"
        f"- Chat type: {escape(chat.type)}\n\n"
        f"<b>Recent activity:</b>\n{activity_lines}"
    )


def stats_text(
    total_users: int,
    total_interactions: int,
    most_active_user: int | None,
    command_counts: dict[str, int],
    last_interaction: str | None,
) -> str:
    if command_counts:
        top_commands = sorted(command_counts.items(), key=lambda item: item[1], reverse=True)
        command_lines = "\n".join(
            f"- {escape(command)}: {count}" for command, count in top_commands[:5]
        )
    else:
        command_lines = "No commands used yet"

    return (
        "<b>Bot Statistics</b>\n\n"
        f"- Total users: {total_users}\n"
        f"- Total interactions: {total_interactions}\n"
        f"- Most active user ID: {most_active_user or 'None'}\n"
        f"- Last interaction: {last_interaction or 'No activity'}\n\n"
        f"<b>Command usage:</b>\n{command_lines}"
    )


def message_reply(text: str, contextual: str) -> str:
    return f'You said: "<i>{escape(text)}</i>"\n\n{escape(contextual)}'
