"""Single ASGI app: MCP at /mcp, plus the webhook and token routes.

Composition the enrichment MCP does not template (it is pure FastMCP). The MCP
Streamable-HTTP app is mounted under a FastAPI parent that also serves the
Telegram webhook, the internal token endpoint, and health. The MCP path is
guarded by the auth seam (bearer now, OAuth as a one-line swap).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telegram.error import TelegramError

from ..config import load_config
from ..db import close_pool
from ..tokens import token_router
from .auth import apply_auth
from .server import mcp
from .webhook import router as webhook_router

logger = logging.getLogger(__name__)

# Serve the MCP endpoint at a stable path and build its ASGI app once.
mcp.settings.streamable_http_path = "/mcp"
_mcp_app = mcp.streamable_http_app()


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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The MCP session manager must run for /mcp to work; nest our startup inside it.
    async with _mcp_app.router.lifespan_context(_mcp_app):
        await _register_webhook()
        yield
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Telegram Launch Gate",
        description="Outbound MCP tools + inbound approval webhook + launch-token endpoint",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(webhook_router)
    app.include_router(token_router)
    # Catch-all mount LAST so the explicit routes above take precedence.
    app.mount("/", _mcp_app)
    return app


# The ASGI entrypoint: FastAPI app wrapped by the auth seam.
app = apply_auth(create_app(), load_config())
