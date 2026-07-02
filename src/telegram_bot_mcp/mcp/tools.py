"""MCP tools: send messages, broadcast, and inspect chats and the bot."""

import asyncio
import json
import logging

from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field
from telegram.error import TelegramError

from ..storage import MessageRecord, store, utc_now_iso
from .app import get_bot, mcp

logger = logging.getLogger(__name__)


class SendMessageRequest(BaseModel):
    """Request model for sending messages."""

    chat_id: int = Field(description="Chat ID to send the message to")
    text: str = Field(description="Message text to send")
    parse_mode: str | None = Field(default="HTML", description="HTML, Markdown, or None")
    reply_to_message_id: int | None = Field(default=None, description="Message ID to reply to")


@mcp.tool()
async def send_telegram_message(request: SendMessageRequest, ctx: Context) -> str:
    """Send a message to a Telegram chat."""
    bot = await get_bot()
    try:
        message = await bot.send_message(
            chat_id=request.chat_id,
            text=request.text,
            parse_mode=request.parse_mode,
            reply_to_message_id=request.reply_to_message_id,
        )
    except TelegramError as exc:
        await ctx.error(f"Failed to send message: {exc}")
        return f"Error sending message: {exc}"

    store.add_message(
        MessageRecord(
            message_id=message.message_id,
            chat_id=message.chat_id,
            user_id=bot.id,
            username=bot.username,
            first_name=bot.first_name,
            text=message.text,
            timestamp=utc_now_iso(),
            message_type="bot_sent",
        )
    )
    await ctx.info(f"Message sent to chat {request.chat_id}")
    return f"Message sent successfully. Message ID: {message.message_id}"


@mcp.tool()
async def get_chat_info(chat_id: int, ctx: Context) -> str:
    """Get information about a Telegram chat."""
    bot = await get_bot()
    try:
        chat = await bot.get_chat(chat_id)
    except TelegramError as exc:
        await ctx.error(f"Failed to get chat info: {exc}")
        return f"Error getting chat info: {exc}"

    info = {
        "id": chat.id,
        "type": chat.type,
        "title": getattr(chat, "title", None),
        "username": getattr(chat, "username", None),
        "first_name": getattr(chat, "first_name", None),
        "last_name": getattr(chat, "last_name", None),
        "description": getattr(chat, "description", None),
    }
    await ctx.info(f"Retrieved chat info for {chat_id}")
    return json.dumps(info, indent=2)


@mcp.tool()
async def broadcast_message(text: str, ctx: Context, parse_mode: str = "HTML") -> str:
    """Broadcast a message to all known users.

    Note: user sessions live in this process's in-memory store. If the MCP
    server runs as a separate process from the bot (combined mode), it only
    sees users that talked to this process. Back the store with a shared
    database for cross-process broadcasts.
    """
    bot = await get_bot()
    sessions = list(store.sessions.values())
    if not sessions:
        return "No users found to broadcast to"

    async def send_one(chat_id: int) -> bool:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            return True
        except TelegramError as exc:
            await ctx.warning(f"Failed to send to chat {chat_id}: {exc}")
            return False

    results = await asyncio.gather(*(send_one(s.chat_id) for s in sessions))
    sent_count = sum(results)
    failed_count = len(results) - sent_count

    result = f"Broadcast completed. Sent to {sent_count} users, {failed_count} failed."
    await ctx.info(result)
    return result


@mcp.tool()
async def get_bot_info(ctx: Context) -> str:
    """Get information about the bot."""
    bot = await get_bot()
    try:
        me = await bot.get_me()
    except TelegramError as exc:
        await ctx.error(f"Failed to get bot info: {exc}")
        return f"Error getting bot info: {exc}"

    info = {
        "id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "is_bot": me.is_bot,
        "can_join_groups": me.can_join_groups,
        "can_read_all_group_messages": me.can_read_all_group_messages,
        "supports_inline_queries": me.supports_inline_queries,
    }
    await ctx.info("Retrieved bot information")
    return json.dumps(info, indent=2)
