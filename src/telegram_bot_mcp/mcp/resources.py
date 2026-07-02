"""MCP resources: message history, active users, and bot statistics."""

import json
import logging

from ..storage import store
from .app import mcp

logger = logging.getLogger(__name__)


@mcp.resource("telegram://messages/recent/{limit}")
async def get_recent_messages(limit: str) -> str:
    """Get recent messages seen or sent by the bot."""
    try:
        limit_int = int(limit)
    except ValueError:
        return f"Invalid limit: {limit}. Must be a number."

    recent = store.recent_messages(limit_int)
    if not recent:
        return "No messages found"

    lines = []
    for message in recent:
        user = message.username or message.first_name or "Unknown"
        lines.append(f"[{message.timestamp}] {user}: {message.text or 'No text'}")
    return "\n".join(lines)


@mcp.resource("telegram://users/active")
async def get_active_users() -> str:
    """Get the list of users known to the bot."""
    if not store.sessions:
        return "No active users found"

    entries = []
    for user_id, session in store.sessions.items():
        entries.append(
            f"User ID: {user_id}\n"
            f"  Username: {session.username or 'N/A'}\n"
            f"  Name: {session.first_name or 'N/A'} {session.last_name or ''}\n"
            f"  Last seen: {session.last_seen or 'N/A'}\n"
        )
    return "\n".join(entries)


@mcp.resource("telegram://stats/summary")
async def get_bot_stats() -> str:
    """Get a summary of bot activity."""
    last_message = store.messages[-1].timestamp if store.messages else "No messages"
    most_active = store.most_active_user()
    return (
        "Bot Statistics Summary\n"
        "======================\n\n"
        f"Total messages: {len(store.messages)}\n"
        f"Total users: {len(store.sessions)}\n\n"
        f"Message types:\n{json.dumps(store.message_type_counts(), indent=2)}\n\n"
        "Recent activity:\n"
        f"- Last message: {last_message}\n"
        f"- Most active user: {most_active if most_active is not None else 'None'}\n"
    )
