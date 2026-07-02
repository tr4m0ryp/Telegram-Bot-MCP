"""Configuration and dependency checks for the --check-config flag."""

import importlib

from ..config import load_config

OPTIONAL_MODULES = ("telegram", "fastapi", "uvicorn", "httpx")
REQUIRED_MODULES = ("mcp", "smithery", "requests", "pydantic")


def _dependency_lines() -> list[str]:
    lines = ["Dependencies:"]
    for name in REQUIRED_MODULES + OPTIONAL_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            required = name in REQUIRED_MODULES
            lines.append(f"  {name}: MISSING{'' if required else ' (install the full extra)'}")
            continue
        version = getattr(module, "__version__", "installed")
        lines.append(f"  {name}: {version}")
    return lines


def check_configuration() -> tuple[bool, str]:
    """Validate configuration and report; returns (ok, report_text)."""
    lines = ["Configuration check", "=" * 40]

    try:
        config = load_config()
    except ValueError as exc:
        lines.append(f"Configuration error: {exc}")
        lines.extend(_dependency_lines())
        return False, "\n".join(lines)

    lines.extend(
        [
            "Telegram:",
            "  bot token: set",
            f"  webhook url: {config.telegram.webhook_url or 'not set'}",
            f"  use webhook: {config.telegram.use_webhook}",
            "Server:",
            f"  host: {config.server.host}",
            f"  port: {config.server.port}",
            f"  mcp port: {config.server.mcp_port}",
            f"  debug: {config.server.debug}",
            f"  log level: {config.server.log_level}",
        ]
    )
    lines.extend(_dependency_lines())
    lines.append("Ready to start.")
    return True, "\n".join(lines)
