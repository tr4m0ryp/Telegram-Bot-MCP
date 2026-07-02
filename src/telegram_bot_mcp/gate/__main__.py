"""Serve the launch gate. Honors Cloud Run's $PORT.

    python -m telegram_bot_mcp.gate
"""

import logging
import os

from ..config import load_config
from .server import run


def main() -> None:
    config = load_config()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, config.server.log_level, logging.INFO),
    )
    # Cloud Run injects PORT; fall back to the configured server port.
    port = int(os.getenv("PORT", str(config.server.port)))
    run(host=config.server.host, port=port)


if __name__ == "__main__":
    main()
