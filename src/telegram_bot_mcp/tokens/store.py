"""Mint, look up, and validate launch tokens.

A launch token is opaque, single-use, time-limited, and bound to both an
engagement and the exact signed Rules-of-Engagement (RoE) hash for that
engagement. Minting happens only from the approval webhook (operator tap);
validation/consumption is the contract the downstream run tool enforces.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..db import get_pool

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32
DEFAULT_TTL_SECONDS = 900


@dataclass(frozen=True)
class MintedToken:
    token: str
    engagement_id: str
    roe_hash: str
    expires_at: datetime


class ValidationError(Exception):
    """Raised when a token fails the validation contract."""


async def lookup_roe_hash(engagement_id: str) -> str | None:
    """Return the signed RoE hash stored for an engagement, or None if unknown."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT roe_hash FROM engagement WHERE engagement_id = $1", engagement_id
    )
    return row["roe_hash"] if row else None


async def mint_token(
    engagement_id: str, roe_hash: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> MintedToken:
    """Create and store a one-time launch token bound to engagement + RoE hash."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO launch_token (token, engagement_id, roe_hash, expires_at)
        VALUES ($1, $2, $3, $4)
        """,
        token,
        engagement_id,
        roe_hash,
        expires_at,
    )
    # Never log the token value.
    logger.info("Minted launch token for engagement %s (ttl %ds)", engagement_id, ttl_seconds)
    return MintedToken(token=token, engagement_id=engagement_id, roe_hash=roe_hash,
                       expires_at=expires_at)


async def validate_and_consume(token: str, engagement_id: str, roe_hash: str) -> None:
    """Atomically validate a token and mark it used, or raise ValidationError.

    Contract: the token exists, is unused, is unexpired, and matches both the
    engagement and the RoE hash. The UPDATE ... WHERE used_at IS NULL clause
    makes consumption single-use even under concurrent callers.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT engagement_id, roe_hash, expires_at, used_at "
                "FROM launch_token WHERE token = $1 FOR UPDATE",
                token,
            )
            if row is None:
                raise ValidationError("unknown token")
            if row["used_at"] is not None:
                raise ValidationError("token already used")
            if row["expires_at"] <= datetime.now(timezone.utc):
                raise ValidationError("token expired")
            if row["engagement_id"] != engagement_id:
                raise ValidationError("engagement mismatch")
            if row["roe_hash"] != roe_hash:
                raise ValidationError("RoE hash mismatch")
            await conn.execute(
                "UPDATE launch_token SET used_at = now() WHERE token = $1", token
            )
    logger.info("Consumed launch token for engagement %s", engagement_id)
