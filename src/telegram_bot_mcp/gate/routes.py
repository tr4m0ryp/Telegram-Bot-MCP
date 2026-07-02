"""Custom HTTP routes on the FastMCP app: health, webhook, and token mint.

These live alongside /mcp (and the OAuth metadata routes the auth provider adds)
but are not part of the MCP protocol and are not behind the MCP OAuth gate — the
webhook self-authenticates (secret header + operator id) and the mint route uses
TOKEN_MINT_SECRET.
"""

import logging

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import load_config
from ..tokens import handle_mint
from .webhook import handle_webhook

logger = logging.getLogger(__name__)


def register_routes(mcp: FastMCP) -> None:
    """Register health, webhook, and (conditionally) the token-mint route."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/telegram/webhook", methods=["POST"])
    async def telegram_webhook(request: Request) -> JSONResponse:
        return await handle_webhook(request)

    # Only expose the HTTP mint route when out-of-process minting is explicitly
    # enabled; by default the webhook mints in-process and this is not mounted.
    if load_config().security.token_mint_secret:

        @mcp.custom_route("/launch-tokens", methods=["POST"])
        async def launch_tokens(request: Request) -> JSONResponse:
            return await handle_mint(request)

        logger.info("Mounted /launch-tokens (TOKEN_MINT_SECRET set)")
