"""Auth seam for the MCP surface — bearer vs OAuth in one place.

Mirrors enrichment-mcp's single-swap design: the mode is chosen by one function
(`apply_auth`) dispatching on MCP_OAUTH_PROVIDER, wired at exactly one call site
(gate/app.py). Nothing else in the service branches on auth mode.

- Static bearer (Claude Code): enforced here by an ASGI middleware that checks
  the Authorization header on the MCP path. Works today, no external provider.
- OAuth (claude.ai web app): claude.ai custom connectors require authorization-
  server metadata discovery + Dynamic Client Registration, which a header check
  cannot provide. Enabling it is a one-line swap — set MCP_OAUTH_PROVIDER=workos
  (plus the WorkOS vars) and mount a FastMCP-v3 auth provider instead of this
  middleware. Until then, web-app connection is unavailable and Claude Code works.
"""

import hmac
import logging
from collections.abc import Awaitable, Callable

from ..config import AppConfig

logger = logging.getLogger(__name__)

ASGIApp = Callable[..., Awaitable[None]]


class BearerAuthMiddleware:
    """Require `Authorization: Bearer <token>` on requests under a path prefix."""

    def __init__(self, app: ASGIApp, token: str, protected_prefix: str = "/mcp") -> None:
        self.app = app
        self.token = token
        self.protected_prefix = protected_prefix

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "http" and scope.get("path", "").startswith(self.protected_prefix):
            if not self._authorized(scope):
                await self._reject(send)
                return
        await self.app(scope, receive, send)

    def _authorized(self, scope: dict) -> bool:
        provided = ""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                header = value.decode("latin-1")
                if header.lower().startswith("bearer "):
                    provided = header[len("bearer ") :]
                break
        return bool(provided) and hmac.compare_digest(provided, self.token)

    @staticmethod
    async def _reject(send: Callable) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})


def apply_auth(app: ASGIApp, config: AppConfig) -> ASGIApp:
    """Wrap the ASGI app with the configured auth mode. The single swap point."""
    provider = (config.security.oauth_provider or "").lower()
    if provider:
        raise NotImplementedError(
            f"OAuth provider '{provider}' requested but not wired in. Mount a FastMCP-v3 "
            "auth provider here (see module docstring) to enable claude.ai connections."
        )

    token = config.security.mcp_bearer_token
    if token:
        logger.info("MCP auth: static bearer")
        return BearerAuthMiddleware(app, token)

    if config.security.allow_unauthenticated:
        logger.warning("MCP auth: DISABLED via MCP_ALLOW_UNAUTHENTICATED — development only")
        return app

    # Fail closed: a missing bearer must not silently open the MCP surface.
    raise ValueError(
        "No MCP auth configured. Set MCP_BEARER_TOKEN (or MCP_OAUTH_PROVIDER), or "
        "MCP_ALLOW_UNAUTHENTICATED=true for local development only."
    )
