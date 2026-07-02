"""The launch-gate FastMCP server: MCP tools + custom routes + auth, one app.

Built on FastMCP v3 (like enrichment-mcp) so the auth layer can be a full OAuth
provider — which is what claude.ai custom connectors require. The two outbound
tools are the only Telegram-facing surface the routine reaches; granting happens
only via the operator's tap on the webhook, out of the routine's reach.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from telegram.error import TelegramError

from ..config import AppConfig, load_config
from ..db import close_pool
from .auth import build_auth
from .routes import register_routes
from .tools import register_tools

logger = logging.getLogger(__name__)


async def _register_webhook() -> None:
    """Point Telegram at our webhook on startup, if a public URL is configured."""
    config = load_config()
    if not config.telegram.webhook_url:
        return
    from .notify import get_bot

    try:
        bot = await get_bot()
        await bot.set_webhook(
            url=config.telegram.webhook_url,
            secret_token=config.telegram.webhook_secret,
            allowed_updates=["callback_query"],
        )
        logger.info("Telegram webhook registered: %s", config.telegram.webhook_url)
    except TelegramError as exc:
        logger.error("Failed to register webhook on startup: %s", exc)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    from .notify import close_bot

    await _register_webhook()
    yield
    await close_bot()
    await close_pool()


def build_server(config: AppConfig | None = None) -> FastMCP:
    """Construct the FastMCP app with auth, the two tools, and the custom routes.

    Construction is pure — no DB or Telegram connection happens here — but it does
    resolve the auth layer, so an unconfigured auth mode fails fast at import.
    """
    config = config or load_config()
    mcp = FastMCP("Telegram Launch Gate", auth=build_auth(config), lifespan=lifespan)
    register_tools(mcp)
    register_routes(mcp)
    return mcp


mcp = build_server()


def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Serve /mcp (+ OAuth metadata), /telegram/webhook, /health over HTTP."""
    logger.info("Serving Telegram Launch Gate at http://%s:%d/mcp", host, port)
    mcp.run(transport="http", host=host, port=port)
