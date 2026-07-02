"""Health, bot info, MCP status, and statistics endpoints."""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from telegram.error import TelegramError
from telegram.ext import Application

from ..storage import utc_now_iso
from .deps import require_application

logger = logging.getLogger(__name__)

router = APIRouter()


async def probe_mcp(client: httpx.AsyncClient) -> dict[str, Any]:
    """Ping the MCP server. Any HTTP response proves reachability.

    The streamable-HTTP MCP endpoint only answers a full JSON-RPC handshake, so
    a plain GET returns 4xx rather than 200 — that still means the server is up.
    Only a transport-level failure counts as down.
    """
    try:
        response = await client.get("/mcp", timeout=5.0)
    except httpx.TimeoutException:
        return {"status": "timeout"}
    except httpx.ConnectError:
        return {"status": "connection_failed"}
    except httpx.HTTPError as exc:
        return {"status": "error", "details": str(exc)}

    return {
        "status": "connected",
        "server_url": str(client.base_url),
        "response_time": response.elapsed.total_seconds(),
    }


async def webhook_info(application: Application) -> dict[str, Any]:
    """Current webhook registration as seen by Telegram."""
    try:
        info = await application.bot.get_webhook_info()
    except TelegramError as exc:
        logger.warning("Could not get webhook info: %s", exc)
        return {"error": str(exc)}

    return {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
        "last_error_message": info.last_error_message,
        "max_connections": info.max_connections,
        "allowed_updates": info.allowed_updates,
    }


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Health of the bot and the MCP server."""
    application: Application | None = getattr(request.app.state, "application", None)
    bot_status = "ok" if application and application.bot else "error"
    mcp_state = await probe_mcp(request.app.state.mcp_client)

    return {
        "status": "healthy" if bot_status == "ok" else "unhealthy",
        "timestamp": utc_now_iso(),
        "services": {
            "telegram_bot": bot_status,
            "mcp_server": mcp_state["status"],
        },
    }


@router.get("/bot/info")
async def get_bot_info(request: Request) -> dict[str, Any]:
    """Bot identity and webhook registration."""
    application = require_application(request)

    try:
        me = await application.bot.get_me()
    except TelegramError as exc:
        logger.error("Error getting bot info: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "bot_info": {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "is_bot": me.is_bot,
            "can_join_groups": me.can_join_groups,
            "can_read_all_group_messages": me.can_read_all_group_messages,
            "supports_inline_queries": me.supports_inline_queries,
        },
        "webhook_info": await webhook_info(application),
    }


@router.get("/mcp/status")
async def get_mcp_status(request: Request) -> dict[str, Any]:
    """MCP server reachability."""
    return await probe_mcp(request.app.state.mcp_client)


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, Any]:
    """Server and bot status summary."""
    application: Application | None = getattr(request.app.state, "application", None)
    return {
        "server": {"timestamp": utc_now_iso()},
        "bot": {"status": "running" if application else "stopped"},
        "mcp": await probe_mcp(request.app.state.mcp_client),
    }
