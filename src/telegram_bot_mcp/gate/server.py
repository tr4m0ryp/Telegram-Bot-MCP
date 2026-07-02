"""The launch-gate MCP server: the only Telegram-facing surface the routine reaches.

Exposes exactly two tools. Neither mints a token, approves, or launches — the
routine is structurally unable to self-approve. Granting happens only via the
operator's tap on the webhook (gate/webhook.py), out of the routine's reach.
"""

import logging

from mcp.server.fastmcp import FastMCP

from ..approval import attach_message, create_pending
from . import notify

logger = logging.getLogger(__name__)

mcp = FastMCP("Telegram Launch Gate")


@mcp.tool()
async def send_notification(text: str) -> str:
    """Send a plain notification to the operator's Telegram chat.

    Use for status pings (lead replied, run complete, needs attention). Sends to
    the configured operator chat only; it cannot target arbitrary chats.
    """
    message_id = await notify.send_notification(text)
    return f"Notification sent (message {message_id})."


@mcp.tool()
async def request_launch_approval(
    engagementId: str, companyName: str, scopeHosts: list[str]
) -> dict:
    """Ask the operator to approve a launch, showing the scope.

    Sends a message that displays the engagement, company, and scope hosts with
    inline Approve / Cancel buttons. This only REQUESTS the gate; it authorizes
    nothing. The button callback carries the engagement id and a random nonce —
    never a token. Returns {"sent": true, "messageId": <id>}.
    """
    nonce = await create_pending(engagementId)
    chat_id, message_id = await notify.send_approval_request(
        engagementId, companyName, scopeHosts, nonce
    )
    await attach_message(engagementId, nonce, chat_id, message_id)
    logger.info("Launch approval requested for engagement %s", engagementId)
    return {"sent": True, "messageId": message_id}
