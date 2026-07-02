"""Smithery-deployed MCP server: session-scoped configuration, send-only tool.

Each connecting client supplies its own bot token and chat ID through the
Smithery session config, so one deployment serves many users without any
server-side credentials.
"""

import logging

import requests
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field
from smithery.decorators import smithery

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10.0


class ConfigSchema(BaseModel):
    """Session-level configuration supplied by the connecting client."""

    telegram_bot_token: str = Field(description="Your Telegram Bot Token from @BotFather")
    telegram_chat_id: str = Field(description="Your Telegram Chat ID")


@smithery.server(config_schema=ConfigSchema)
def create_server() -> FastMCP:
    """Create and configure the Telegram Bot MCP server."""
    server = FastMCP("Telegram Bot MCP")

    @server.tool()
    def send_telegram_message(text: str, ctx: Context) -> str:
        """Send a message to the configured Telegram chat."""
        session_config = ctx.session_config
        token = session_config.telegram_bot_token
        url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": session_config.telegram_chat_id, "text": text},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            payload = response.json()
        except requests.RequestException as exc:
            # Redact the token: requests errors embed the request URL.
            detail = str(exc).replace(token, "***")
            logger.error("Telegram API request failed: %s", detail)
            return f"Error sending message: {detail}"

        if payload.get("ok"):
            return "Message sent successfully."
        return f"Error sending message: {payload.get('description', 'unknown error')}"

    @server.resource("telegram://about")
    def about_telegram() -> str:
        """Information about using this Telegram Bot MCP server."""
        return (
            "Telegram Bot MCP Server\n\n"
            "Sends messages to Telegram chats via the Telegram Bot API.\n\n"
            "Configuration required:\n"
            "- telegram_bot_token: from @BotFather on Telegram\n"
            "- telegram_chat_id: your chat or channel ID (see @userinfobot)\n\n"
            "Tools:\n"
            "- send_telegram_message: send a text message to the configured chat\n"
        )

    @server.prompt()
    def telegram_message(recipient: str, message: str) -> list[dict[str, str]]:
        """Generate a prompt for sending a Telegram message."""
        return [
            {
                "role": "user",
                "content": f"Send this message to {recipient} via Telegram: {message}",
            },
        ]

    return server
