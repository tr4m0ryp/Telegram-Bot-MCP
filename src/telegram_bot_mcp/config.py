"""Environment-backed configuration.

Loaded lazily via load_config() so that importing the package never requires
environment variables; only the entry points that need credentials fail fast.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value else None


@dataclass
class TelegramConfig:
    """Telegram bot credentials, webhook settings, and the operator identity."""

    bot_token: str
    webhook_url: str | None = None
    webhook_secret: str | None = None
    # The single Telegram user whose taps the approval webhook honors, and the
    # chat outbound notifications are sent to.
    operator_user_id: int | None = None
    operator_chat_id: int | None = None

    @property
    def use_webhook(self) -> bool:
        return self.webhook_url is not None

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        return cls(
            bot_token=bot_token,
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            webhook_secret=os.getenv("WEBHOOK_SECRET"),
            operator_user_id=_int_or_none(os.getenv("OPERATOR_TELEGRAM_USER_ID")),
            operator_chat_id=_int_or_none(os.getenv("OPERATOR_CHAT_ID")),
        )


@dataclass
class SecurityConfig:
    """Secrets guarding the MCP surface and the internal token-mint endpoint."""

    # Static bearer for Claude Code; the OAuth path (claude.ai) is a separate seam.
    mcp_bearer_token: str | None = None
    # Empty = bearer mode. Non-empty (e.g. "workos") selects an OAuth provider,
    # mirroring enrichment-mcp's MCP_OAUTH_PROVIDER single-swap.
    oauth_provider: str | None = None
    # Guards POST /launch-tokens when it is reachable out-of-process. Same-process
    # calls from the webhook use the in-process minter and never present this.
    token_mint_secret: str | None = None
    # Public HTTPS base used to register the Telegram webhook and advertise OAuth.
    public_url: str | None = None

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        return cls(
            mcp_bearer_token=os.getenv("MCP_BEARER_TOKEN"),
            oauth_provider=os.getenv("MCP_OAUTH_PROVIDER"),
            token_mint_secret=os.getenv("TOKEN_MINT_SECRET"),
            public_url=os.getenv("PUBLIC_URL"),
        )


@dataclass
class DatabaseConfig:
    """Connection to the launch_token store (reuses the enrichment Postgres)."""

    url: str | None = None

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(url=os.getenv("DATABASE_URL"))

    def require_url(self) -> str:
        if not self.url:
            raise ValueError("DATABASE_URL is required for the launch-token store")
        return self.url


@dataclass
class ServerConfig:
    """Webhook and MCP server network settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    mcp_port: int = 8001
    debug: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8000")),
            mcp_port=int(os.getenv("MCP_PORT", "8001")),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


@dataclass
class AppConfig:
    """Aggregate application configuration."""

    telegram: TelegramConfig
    server: ServerConfig
    security: SecurityConfig
    database: DatabaseConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            telegram=TelegramConfig.from_env(),
            server=ServerConfig.from_env(),
            security=SecurityConfig.from_env(),
            database=DatabaseConfig.from_env(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Configuration as a dictionary with secrets masked."""
        return {
            "telegram": {
                "bot_token": "***" if self.telegram.bot_token else None,
                "webhook_url": self.telegram.webhook_url,
                "use_webhook": self.telegram.use_webhook,
                "operator_user_id": self.telegram.operator_user_id,
                "operator_chat_id": self.telegram.operator_chat_id,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "mcp_port": self.server.mcp_port,
                "debug": self.server.debug,
                "log_level": self.server.log_level,
            },
            "security": {
                "mcp_bearer_token": "***" if self.security.mcp_bearer_token else None,
                "token_mint_secret": "***" if self.security.token_mint_secret else None,
                "public_url": self.security.public_url,
            },
            "database": {"url": "***" if self.database.url else None},
        }


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load configuration from .env and the environment, cached per process."""
    load_dotenv()
    return AppConfig.from_env()
