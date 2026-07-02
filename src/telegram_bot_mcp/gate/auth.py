"""Auth seam for the MCP surface — bearer vs OAuth in one place.

Mirrors enrichment-mcp's single-swap design: one function (`build_auth`)
selects the provider from `MCP_OAUTH_PROVIDER`, and nothing else in the service
branches on auth mode. Provider classes are imported lazily so an unused
optional dependency never loads.

- static bearer (Claude Code): `StaticTokenVerifier` when `MCP_BEARER_TOKEN` is
  set and no provider is selected.
- `workos` (claude.ai web): `WorkOSProvider` runs the OAuth proxy — FastMCP does
  Dynamic Client Registration for the claude.ai connector and proxies login to
  AuthKit. This is what claude.ai custom connectors require.
- `oidc`: any OIDC provider via `OIDCProxy` (FastMCP performs DCR itself).

Fails closed: with no provider and no bearer, the server refuses to start unless
`MCP_ALLOW_UNAUTHENTICATED=true` is set explicitly (local dev only).
"""

import logging

from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from ..config import AppConfig

logger = logging.getLogger(__name__)

_BEARER_CLIENT_ID = "telegram-launch-gate"


def build_auth(config: AppConfig) -> AuthProvider | None:
    """Return the server's single auth layer, or None for opted-in authless dev."""
    provider = (config.security.oauth_provider or "").lower()
    if provider == "workos":
        return _workos(config)
    if provider == "oidc":
        return _oidc(config)
    if provider:
        raise ValueError(
            f"Unknown MCP_OAUTH_PROVIDER={provider!r}; use 'workos', 'oidc', or "
            "leave empty for bearer."
        )

    if config.security.mcp_bearer_token:
        logger.info("MCP auth: static bearer")
        return StaticTokenVerifier(
            tokens={config.security.mcp_bearer_token: {"client_id": _BEARER_CLIENT_ID,
                                                       "scopes": []}}
        )

    if config.security.allow_unauthenticated:
        logger.warning("MCP auth: DISABLED via MCP_ALLOW_UNAUTHENTICATED — development only")
        return None

    raise ValueError(
        "No MCP auth configured. Set MCP_OAUTH_PROVIDER (workos/oidc) for claude.ai, "
        "MCP_BEARER_TOKEN for Claude Code, or MCP_ALLOW_UNAUTHENTICATED=true for local dev."
    )


def _require(config: AppConfig, *fields: str) -> None:
    missing = [f for f in fields if not getattr(config.security, f, None)]
    if missing:
        env = {
            "workos_authkit_domain": "WORKOS_AUTHKIT_DOMAIN",
            "workos_client_id": "WORKOS_CLIENT_ID",
            "workos_client_secret": "WORKOS_CLIENT_SECRET",
            "mcp_base_url": "MCP_BASE_URL (or PUBLIC_URL)",
            "oidc_config_url": "MCP_OIDC_CONFIG_URL",
            "oidc_client_id": "MCP_OIDC_CLIENT_ID",
        }
        names = ", ".join(env.get(f, f) for f in missing)
        raise ValueError(f"MCP_OAUTH_PROVIDER requires: {names}")


def _workos(config: AppConfig) -> AuthProvider:
    """OAuth via WorkOS AuthKit using the full WorkOSProvider (OAuth proxy)."""
    from fastmcp.server.auth.providers.workos import WorkOSProvider

    _require(config, "workos_authkit_domain", "workos_client_id", "workos_client_secret",
             "mcp_base_url")
    logger.info("MCP auth: WorkOS OAuth proxy (resource=%s)", config.security.mcp_base_url)
    return WorkOSProvider(
        client_id=config.security.workos_client_id,
        client_secret=config.security.workos_client_secret,
        authkit_domain=config.security.workos_authkit_domain,
        base_url=config.security.mcp_base_url,
    )


def _oidc(config: AppConfig) -> AuthProvider:
    """OAuth via any OIDC provider (Auth0 / Google / Descope / WorkOS-manual)."""
    from fastmcp.server.auth.oidc_proxy import OIDCProxy

    _require(config, "oidc_config_url", "oidc_client_id", "mcp_base_url")
    logger.info("MCP auth: OIDC OAuth (config_url=%s)", config.security.oidc_config_url)
    return OIDCProxy(
        config_url=config.security.oidc_config_url,
        client_id=config.security.oidc_client_id,
        client_secret=config.security.oidc_client_secret or None,
        base_url=config.security.mcp_base_url,
    )
