"""Internal launch-token endpoint: POST /launch-tokens.

Reachable ONLY by this service's own webhook handler. Two guards, whichever
applies to the deployment:
  - same-process: the webhook calls mint_token() directly and never touches HTTP.
  - out-of-process: requests must carry the TOKEN_MINT_SECRET bearer.
It is never guarded by the MCP bearer and never holds anything the routine can
reach — that is what keeps the human gate real.
"""

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import load_config
from .store import DEFAULT_TTL_SECONDS, mint_token

logger = logging.getLogger(__name__)

router = APIRouter()


class MintRequest(BaseModel):
    engagement_id: str = Field(alias="engagementId")
    roe_hash: str = Field(alias="roeHash")
    ttl_seconds: int = Field(default=DEFAULT_TTL_SECONDS, alias="ttlSeconds", ge=1)

    model_config = {"populate_by_name": True}


class MintResponse(BaseModel):
    token: str
    engagement_id: str
    expires_at: str


def _require_mint_secret(authorization: str | None) -> None:
    """Enforce the TOKEN_MINT_SECRET bearer for out-of-process callers."""
    secret = load_config().security.token_mint_secret
    if not secret:
        # No secret configured: out-of-process minting is disabled. The webhook
        # must use the in-process minter instead of this HTTP route.
        raise HTTPException(status_code=503, detail="Token minting over HTTP is disabled")
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[len("bearer ") :]
    if not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Invalid mint secret")


@router.post("/launch-tokens", response_model=MintResponse)
async def create_launch_token(
    request: MintRequest, authorization: str | None = Header(default=None)
) -> MintResponse:
    """Mint a one-time launch token. Internal callers only."""
    _require_mint_secret(authorization)
    minted = await mint_token(request.engagement_id, request.roe_hash, request.ttl_seconds)
    return MintResponse(
        token=minted.token,
        engagement_id=minted.engagement_id,
        expires_at=minted.expires_at.isoformat(),
    )
