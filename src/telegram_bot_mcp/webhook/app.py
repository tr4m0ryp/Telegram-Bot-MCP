"""FastAPI application wiring: lifespan, routers, and the root endpoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from telegram.error import TelegramError

from ..bot import BotRunner
from ..config import load_config
from ..storage import utc_now_iso
from . import admin, status, telegram

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the bot and the MCP status client; tear both down on exit."""
    config = load_config()

    runner = BotRunner()
    await runner.initialize()
    await runner.application.initialize()
    app.state.application = runner.application
    app.state.webhook_secret = config.telegram.webhook_secret
    # The MCP server runs as a co-located subprocess in combined mode, so probe
    # it on the loopback interface regardless of the configured bind host.
    app.state.mcp_client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{config.server.mcp_port}",
        timeout=httpx.Timeout(30.0),
    )

    if config.telegram.webhook_url:
        try:
            await runner.application.bot.set_webhook(
                url=config.telegram.webhook_url,
                secret_token=config.telegram.webhook_secret,
            )
            logger.info("Webhook registered with Telegram: %s", config.telegram.webhook_url)
        except TelegramError as exc:
            logger.error("Failed to register webhook on startup: %s", exc)

    logger.info("Webhook server initialized")

    yield

    await app.state.application.shutdown()
    await app.state.mcp_client.aclose()
    logger.info("Webhook server shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Telegram Bot MCP Webhook Server",
        description="Production webhook server for the Telegram bot with MCP integration",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(telegram.router)
    app.include_router(status.router)
    app.include_router(admin.router)

    @app.get("/")
    async def root() -> dict[str, object]:
        """Server information."""
        return {
            "service": "Telegram Bot MCP Webhook Server",
            "version": "0.2.0",
            "status": "running",
            "timestamp": utc_now_iso(),
            "endpoints": {
                "webhook": "/webhook",
                "health": "/health",
                "bot_info": "/bot/info",
                "mcp_status": "/mcp/status",
                "stats": "/stats",
            },
        }

    return app


app = create_app()
