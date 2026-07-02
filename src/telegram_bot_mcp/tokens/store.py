"""Mint, look up, and validate launch tokens.

A launch token is opaque, single-use, time-limited, and bound to both an
engagement and the exact signed Rules-of-Engagement (RoE) hash for that
engagement. It is minted only inside the operator-approval transaction
(approve_pending_and_mint), never by anything the routine can reach, and its
value is never returned to Claude. A downstream run tool that shares this
database redeems it with claim_token_for_engagement (or validate_and_consume if
it was delivered the value out-of-band).
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg

from ..db import get_pool

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32
DEFAULT_TTL_SECONDS = 900
# A pending approval older than this is stale and can no longer be approved.
PENDING_TTL_SECONDS = 900


@dataclass(frozen=True)
class MintedToken:
    token: str
    engagement_id: str
    roe_hash: str
    expires_at: datetime


@dataclass(frozen=True)
class Engagement:
    engagement_id: str
    company_name: str
    scope_hosts: list[str]
    roe_hash: str


class ValidationError(Exception):
    """Raised when a token fails the validation contract."""


async def get_engagement(engagement_id: str) -> Engagement | None:
    """Return the signed engagement record, or None if unknown/unsigned.

    Treats a missing row or a blank roe_hash as "no signed scope" — the gate
    fails closed rather than minting against an empty binding.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT engagement_id, company_name, scope_hosts, roe_hash "
        "FROM engagement WHERE engagement_id = $1",
        engagement_id,
    )
    if row is None or not (row["roe_hash"] or "").strip():
        return None
    return Engagement(
        engagement_id=row["engagement_id"],
        company_name=row["company_name"],
        scope_hosts=list(row["scope_hosts"]),
        roe_hash=row["roe_hash"],
    )


async def lookup_roe_hash(engagement_id: str) -> str | None:
    """Return the signed RoE hash for an engagement, or None if unknown/blank."""
    engagement = await get_engagement(engagement_id)
    return engagement.roe_hash if engagement else None


def _new_token(engagement_id: str, roe_hash: str, ttl_seconds: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    return token, expires_at


async def _insert_token(
    conn: asyncpg.Connection, engagement_id: str, roe_hash: str, ttl_seconds: int
) -> MintedToken:
    """Insert a token row on an existing connection (joins a caller transaction)."""
    token, expires_at = _new_token(engagement_id, roe_hash, ttl_seconds)
    await conn.execute(
        "INSERT INTO launch_token (token, engagement_id, roe_hash, expires_at) "
        "VALUES ($1, $2, $3, $4)",
        token,
        engagement_id,
        roe_hash,
        expires_at,
    )
    logger.info("Minted launch token for engagement %s (ttl %ds)", engagement_id, ttl_seconds)
    return MintedToken(token, engagement_id, roe_hash, expires_at)


async def mint_token(
    engagement_id: str, roe_hash: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> MintedToken:
    """Create and store a one-time launch token bound to engagement + RoE hash."""
    if not roe_hash.strip():
        raise ValueError("refusing to mint against an empty RoE hash")
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _insert_token(conn, engagement_id, roe_hash, ttl_seconds)


async def approve_pending_and_mint(
    engagement_id: str, nonce: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> MintedToken | None:
    """Atomically approve a still-pending request and mint its token.

    One transaction: lock the pending row (must be 'pending' and within the TTL),
    mint a token bound to the roe_hash SNAPSHOTTED at request time, then flip the
    row to 'approved'. Either both happen or neither, so a tap can never leave an
    approved-but-tokenless dead state. Returns None for a stale/replayed/unknown
    tap (nothing was minted).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT roe_hash FROM pending_approval "
                "WHERE engagement_id = $1 AND nonce = $2 AND status = 'pending' "
                "AND created_at > now() - ($3 || ' seconds')::interval "
                "FOR UPDATE",
                engagement_id,
                nonce,
                str(PENDING_TTL_SECONDS),
            )
            if row is None:
                return None
            roe_hash = (row["roe_hash"] or "").strip()
            if not roe_hash:
                # Snapshot should never be blank (validated at request time); fail closed.
                logger.error("Pending approval for %s had blank RoE snapshot", engagement_id)
                return None
            minted = await _insert_token(conn, engagement_id, roe_hash, ttl_seconds)
            await conn.execute(
                "UPDATE pending_approval SET status = 'approved', resolved_at = now() "
                "WHERE engagement_id = $1 AND nonce = $2",
                engagement_id,
                nonce,
            )
    return minted


async def validate_and_consume(token: str, engagement_id: str, roe_hash: str) -> None:
    """Atomically validate a token and mark it used, or raise ValidationError.

    Single-use is enforced by BOTH the FOR UPDATE row lock and the
    `AND used_at IS NULL` guard on the UPDATE, so the invariant survives even if
    one is later removed.
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
                "UPDATE launch_token SET used_at = now() "
                "WHERE token = $1 AND used_at IS NULL",
                token,
            )
    logger.info("Consumed launch token for engagement %s", engagement_id)


async def claim_token_for_engagement(engagement_id: str, roe_hash: str) -> MintedToken | None:
    """Atomically consume the single valid token for an engagement, if any.

    Redemption path for a downstream run tool that shares this database and was
    not handed the opaque token value (which never returns through Claude). Marks
    exactly one unused, unexpired, matching token as used and returns it.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT token, expires_at FROM launch_token "
                "WHERE engagement_id = $1 AND roe_hash = $2 AND used_at IS NULL "
                "AND expires_at > now() "
                "ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                engagement_id,
                roe_hash,
            )
            if row is None:
                return None
            await conn.execute(
                "UPDATE launch_token SET used_at = now() "
                "WHERE token = $1 AND used_at IS NULL",
                row["token"],
            )
    logger.info("Claimed launch token for engagement %s", engagement_id)
    return MintedToken(row["token"], engagement_id, roe_hash, row["expires_at"])
