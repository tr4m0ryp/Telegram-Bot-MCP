"""Serve the launch gate. Honors Cloud Run's $PORT.

    python -m telegram_bot_mcp.gate
"""

import logging
import os

import uvicorn

from ..config import load_config


def main() -> None:
    config = load_config()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, config.server.log_level, logging.INFO),
    )
    # Cloud Run injects PORT; fall back to the configured server port.
    port = int(os.getenv("PORT", str(config.server.port)))
    uvicorn.run(
        "telegram_bot_mcp.gate.app:app",
        host=config.server.host,
        port=port,
        log_level=config.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()
