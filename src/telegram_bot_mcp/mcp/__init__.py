"""Full-featured MCP server backed by a server-side bot token."""

from .app import get_bot, mcp, run
from . import prompts, resources, tools  # noqa: F401  (register handlers on import)

__all__ = ["mcp", "run", "get_bot"]
