"""Environment-backed configuration.

Loaded lazily via load_config() so that importing the package never requires
environment variables; only the entry points that need credentials fail fast.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv


@dataclass
class TelegramConfig:
    """Telegram bot credentials and webhook settings."""

    bot_token: str
    webhook_url: str | None = None
    webhook_secret: str | None = None

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
        )


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

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(telegram=TelegramConfig.from_env(), server=ServerConfig.from_env())

    def to_dict(self) -> dict[str, Any]:
        """Configuration as a dictionary with secrets masked."""
        return {
            "telegram": {
                "bot_token": "***" if self.telegram.bot_token else None,
                "webhook_url": self.telegram.webhook_url,
                "use_webhook": self.telegram.use_webhook,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "mcp_port": self.server.mcp_port,
                "debug": self.server.debug,
                "log_level": self.server.log_level,
            },
        }


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load configuration from .env and the environment, cached per process."""
    load_dotenv()
    return AppConfig.from_env()
