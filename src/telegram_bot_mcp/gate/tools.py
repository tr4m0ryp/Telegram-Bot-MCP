"""The two outbound MCP tools — the only Telegram-facing surface the routine reaches.

Neither mints a token, approves, or launches. Granting happens only via the
operator's tap on the webhook, out of the routine's reach.
"""

import logging

from fastmcp import FastMCP

from ..approval import attach_message, create_pending, delete_pending, valid_engagement_id
from ..tokens import get_engagement
from . import notify

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP) -> None:
    """Register the outbound tools on the FastMCP server."""

    @mcp.tool
    async def send_notification(text: str) -> str:
        """Send a plain notification to the operator's Telegram chat.

        Use for status pings (lead replied, run complete, needs attention). Sends
        to the configured operator chat only; it cannot target arbitrary chats.
        """
        message_id = await notify.send_notification(text)
        return f"Notification sent (message {message_id})."

    @mcp.tool
    async def request_launch_approval(
        engagementId: str, companyName: str, scopeHosts: list[str]
    ) -> dict:
        """Ask the operator to approve a launch, showing the SIGNED scope.

        The message displays the engagement's signed company + scope hosts (from
        the verified record, not these arguments) with inline Approve / Cancel
        buttons, and flags any mismatch with what the routine requested. This only
        REQUESTS the gate; it authorizes nothing. The button callback carries the
        engagement id and a random nonce — never a token. Returns
        {"sent": true, "messageId": <id>} or {"sent": false, "error": <reason>}.
        """
        if not valid_engagement_id(engagementId):
            return {"sent": False, "error": "invalid engagementId (use [A-Za-z0-9_-], <=28 chars)"}

        engagement = await get_engagement(engagementId)
        if engagement is None:
            return {"sent": False, "error": "unknown or unsigned engagement"}

        nonce = await create_pending(
            engagementId, engagement.roe_hash, engagement.company_name, engagement.scope_hosts
        )
        try:
            chat_id, message_id = await notify.send_approval_request(
                engagementId, nonce, engagement.company_name, engagement.scope_hosts,
                companyName, scopeHosts,
            )
        except Exception as exc:  # noqa: BLE001 — clean up the orphan, report to caller
            await delete_pending(engagementId, nonce)
            logger.error("Failed to send approval request for %s: %s", engagementId, exc)
            return {"sent": False, "error": f"could not send approval request: {exc}"}

        await attach_message(engagementId, nonce, chat_id, message_id)
        logger.info("Launch approval requested for engagement %s", engagementId)
        return {"sent": True, "messageId": message_id}
