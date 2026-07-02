"""Command-line argument parsing for the unified launcher."""

import argparse

EPILOG = """\
Examples:
  telegram-bot-mcp                    # polling mode (default)
  telegram-bot-mcp --webhook          # webhook mode
  telegram-bot-mcp --mcp              # MCP server only
  telegram-bot-mcp --combined         # webhook + MCP server
  telegram-bot-mcp --check-config     # validate configuration and exit
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-bot-mcp",
        description="Telegram Bot MCP unified launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--polling", action="store_true", help="Start in polling mode (default)"
    )
    mode_group.add_argument("--webhook", action="store_true", help="Start in webhook mode")
    mode_group.add_argument("--mcp", action="store_true", help="Start the MCP server only")
    mode_group.add_argument(
        "--combined", action="store_true", help="Start both webhook and MCP server"
    )

    parser.add_argument("--host", default=None, help="Server host (default: from environment)")
    parser.add_argument(
        "--port", type=int, default=None, help="Webhook server port (default: from environment)"
    )
    parser.add_argument(
        "--mcp-port", type=int, default=None, help="MCP server port (default: from environment)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log level (default: from environment)",
    )
    parser.add_argument(
        "--check-config", action="store_true", help="Check configuration and exit"
    )
    return parser
