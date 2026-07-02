"""Pending-approval lifecycle.

Each approval request the routine sends creates a pending row carrying a random
nonce and a SNAPSHOT of the engagement's signed scope + RoE hash. The nonce
(never a token) rides in the inline-button callback data. Approval is resolved
atomically together with minting (see tokens.approve_pending_and_mint); this
module handles creation, cleanup, and cancellation.
"""

import logging
import re
import secrets

from ..db import get_pool

logger = logging.getLogger(__name__)

NONCE_BYTES = 16
# Bounds engagement_id so the encoded callback_data stays under Telegram's 64-byte
# cap and cannot contain the ':' separator used by the callback codec.
ENGAGEMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,28}$")
PENDING_TTL_SECONDS = 900


def valid_engagement_id(engagement_id: str) -> bool:
    return bool(ENGAGEMENT_ID_RE.match(engagement_id))


async def create_pending(
    engagement_id: str, roe_hash: str, company_name: str, scope_hosts: list[str]
) -> str:
    """Create a pending approval snapshotting the signed scope; return its nonce."""
    nonce = secrets.token_urlsafe(NONCE_BYTES)
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO pending_approval
            (engagement_id, nonce, roe_hash, company_name, scope_hosts, status)
        VALUES ($1, $2, $3, $4, $5, 'pending')
        """,
        engagement_id,
        nonce,
        roe_hash,
        company_name,
        scope_hosts,
    )
    return nonce


async def attach_message(engagement_id: str, nonce: str, chat_id: int, message_id: int) -> None:
    """Record which Telegram message carries this approval's buttons."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE pending_approval SET chat_id = $3, message_id = $4 "
        "WHERE engagement_id = $1 AND nonce = $2",
        engagement_id,
        nonce,
        chat_id,
        message_id,
    )


async def delete_pending(engagement_id: str, nonce: str) -> None:
    """Remove a pending row (e.g. when sending its Telegram message failed)."""
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM pending_approval WHERE engagement_id = $1 AND nonce = $2",
        engagement_id,
        nonce,
    )


async def cancel_pending(engagement_id: str, nonce: str) -> bool:
    """Transition a still-pending, non-stale approval to 'cancelled'.

    Returns True only if a pending row matched; False for unknown/already-resolved
    (replay/stale) taps.
    """
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE pending_approval SET status = 'cancelled', resolved_at = now() "
        "WHERE engagement_id = $1 AND nonce = $2 AND status = 'pending' "
        "AND created_at > now() - ($3 || ' seconds')::interval",
        engagement_id,
        nonce,
        str(PENDING_TTL_SECONDS),
    )
    return result.endswith(" 1")
