"""Example MCP client: list tools and send a test message over streamable HTTP."""

import asyncio
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = "http://localhost:8081/mcp"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with streamablehttp_client(SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            logger.info("Available tools: %s", [tool.name for tool in tools.tools])

            result = await session.call_tool("send_telegram_message", {"text": "Hello, World!"})
            logger.info("Tool result: %s", result.content)


if __name__ == "__main__":
    asyncio.run(main())
