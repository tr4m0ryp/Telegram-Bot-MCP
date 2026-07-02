"""Internal launch-token endpoint handler: POST /launch-tokens (Starlette).

Reachable ONLY by this service's own webhook handler. When exposed out-of-process
it must carry the TOKEN_MINT_SECRET bearer; the route is registered only when that
secret is set (gate/routes.py), so by default it does not exist. It is never
guarded by the MCP bearer and never holds anything the routine can reach.
"""

import hmac
import json
import logging

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import load_config
from .store import DEFAULT_TTL_SECONDS, mint_token

logger = logging.getLogger(__name__)


class MintRequest(BaseModel):
    engagement_id: str = Field(alias="engagementId")
    roe_hash: str = Field(alias="roeHash")
    ttl_seconds: int = Field(default=DEFAULT_TTL_SECONDS, alias="ttlSeconds", ge=1)

    model_config = {"populate_by_name": True}


def _mint_secret_ok(request: Request) -> bool:
    secret = load_config().security.token_mint_secret
    if not secret:
        return False
    auth = request.headers.get("authorization", "")
    provided = auth[len("bearer ") :] if auth.lower().startswith("bearer ") else ""
    return hmac.compare_digest(provided, secret)


async def handle_mint(request: Request) -> JSONResponse:
    """Mint a one-time launch token. Internal callers only."""
    if not _mint_secret_ok(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    try:
        body = await request.json()
        req = MintRequest(**body)
    except (json.JSONDecodeError, ValidationError) as exc:
        return JSONResponse({"error": f"invalid request: {exc}"}, status_code=400)

    minted = await mint_token(req.engagement_id, req.roe_hash, req.ttl_seconds)
    return JSONResponse(
        {
            "token": minted.token,
            "engagement_id": minted.engagement_id,
            "expires_at": minted.expires_at.isoformat(),
        }
    )
