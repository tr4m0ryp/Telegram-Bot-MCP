"""Entry point: python -m telegram_bot_mcp.mcp [--host HOST] [--port PORT]"""

import argparse
import logging

from . import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram Bot MCP server (streamable HTTP)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port (default: 8001)")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
