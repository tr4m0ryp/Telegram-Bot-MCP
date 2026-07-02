"""FastMCP application exposing the full Telegram tool surface.

Uses the server-side TELEGRAM_BOT_TOKEN from the environment, unlike the
Smithery entry point in server.py which takes per-session credentials.
"""

import logging

from mcp.server.fastmcp import FastMCP
from telegram import Bot

from ..config import load_config

logger = logging.getLogger(__name__)

mcp = FastMCP("Telegram Bot MCP")

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


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    """Serve the MCP server over streamable HTTP. Blocks until interrupted."""
    mcp.settings.host = host
    mcp.settings.port = port
    logger.info("Starting MCP server on %s:%d", host, port)
    mcp.run(transport="streamable-http")
