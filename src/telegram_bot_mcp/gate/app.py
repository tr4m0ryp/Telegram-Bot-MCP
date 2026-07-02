"""ASGI entrypoint for the launch gate.

`app` is the FastMCP Streamable-HTTP application: it serves /mcp, the OAuth
metadata + proxy routes added by the auth provider, and the custom /health,
/telegram/webhook, and /launch-tokens routes. Serve it with `uvicorn
telegram_bot_mcp.gate.app:app`, or run `python -m telegram_bot_mcp.gate`.
"""

from .server import mcp

app = mcp.http_app()

__all__ = ["app"]
