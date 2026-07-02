"""Pending-approval lifecycle.

Each approval request the routine sends creates a pending row carrying a random
nonce. The nonce (never a token) rides in the inline-button callback data. When
the operator taps, the webhook resolves the pending row by (engagement_id,
nonce): a still-pending match transitions to approved/cancelled exactly once, so
a replayed or stale tap finds nothing to act on.
"""

import logging
import secrets
from dataclasses import dataclass

from ..db import get_pool

logger = logging.getLogger(__name__)

NONCE_BYTES = 16


@dataclass(frozen=True)
class PendingApproval:
    engagement_id: str
    nonce: str


async def create_pending(engagement_id: str) -> str:
    """Create a pending approval for an engagement and return its nonce."""
    nonce = secrets.token_urlsafe(NONCE_BYTES)
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO pending_approval (engagement_id, nonce, status)
        VALUES ($1, $2, 'pending')
        """,
        engagement_id,
        nonce,
    )
    return nonce


async def attach_message(engagement_id: str, nonce: str, chat_id: int, message_id: int) -> None:
    """Record which Telegram message carries this approval's buttons."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE pending_approval SET chat_id = $3, message_id = $4
        WHERE engagement_id = $1 AND nonce = $2
        """,
        engagement_id,
        nonce,
        chat_id,
        message_id,
    )


async def resolve_pending(engagement_id: str, nonce: str, decision: str) -> bool:
    """Transition a still-pending approval to 'approved' or 'cancelled'.

    Returns True only if a pending row matched and was transitioned by this call;
    False for an unknown nonce or one that was already resolved (replay/stale).
    """
    if decision not in ("approved", "cancelled"):
        raise ValueError(f"invalid decision: {decision}")

    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE pending_approval
        SET status = $3, resolved_at = now()
        WHERE engagement_id = $1 AND nonce = $2 AND status = 'pending'
        """,
        engagement_id,
        nonce,
        decision,
    )
    # asyncpg returns e.g. "UPDATE 1" / "UPDATE 0".
    updated = result.endswith(" 1")
    if not updated:
        logger.warning("Approval resolve no-op for engagement %s (replayed or unknown)",
                       engagement_id)
    return updated
