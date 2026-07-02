"""Deployable launch-gate service: outbound MCP + inbound approval webhook + tokens.

The ASGI entrypoint is `telegram_bot_mcp.gate.app:app`. Importing this package
does not build the app or require configuration; the entrypoint module does.
"""

__all__: list[str] = []
