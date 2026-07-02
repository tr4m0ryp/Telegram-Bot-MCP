"""Async Postgres pool for the launch-token store.

A single process-wide asyncpg pool, created lazily. The schema is applied on
first connection so a fresh database (or the shared enrichment Postgres) is
ready without a separate migration step.
"""

import logging
from pathlib import Path

import asyncpg

from ..config import load_config

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it and the schema on first use."""
    global _pool
    if _pool is None:
        url = load_config().database.require_url()
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA_PATH.read_text())
        logger.info("Launch-token database pool ready")
    return _pool


async def close_pool() -> None:
    """Close the pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
