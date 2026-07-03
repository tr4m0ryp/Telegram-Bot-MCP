"""Async Postgres pool shared by the token and approval stores.

A single process-wide asyncpg pool, created lazily. The schema is applied on
first connection so a fresh database (or the shared enrichment Postgres) is
ready without a separate migration step. Mirrors enrichment-mcp's db/pool.py:
plain DSN over TCP, small max_size to stay under session-pooler client caps.
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
        # search_path pins every connection to the gate's own schema, so its
        # tables never collide with the host database's.
        _pool = await asyncpg.create_pool(
            url, min_size=1, max_size=2, server_settings={"search_path": "launch_gate"}
        )
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA_PATH.read_text())
        logger.info("Database pool ready")
    return _pool


async def close_pool() -> None:
    """Close the pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
