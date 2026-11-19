"""Reference solution. Sign-in: the identity of a request, from an access token of Keycloak. Phase 5, week 19.

The API and the two MCP servers accept a request only with a valid access token of the realm
`lab`. A token of a test user holds these claims (make token AS=analyst ARGS=--claims):

    iss                 http://localhost:8180/realms/lab (AUTH_ISSUER)
    aud                 ["assistant-api", "mcp-sql", "mcp-catalogue"]
    scope               "openid profile mcp:tools"
    preferred_username  "analyst"
    groups              ["analysts"]   (no claim for a user without a group)
    exp, iat, sub, azp  as in each token

Each service accepts only tokens with its own audience: the API `assistant-api`
(API_AUDIENCE), the SQL server `mcp-sql` and the catalogue server `mcp-catalogue`.

service_token() is complete. Write verify(), and use it in the API and in a TokenVerifier of
each MCP server, as the MCP authorization tutorial shows.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from assistant.config import get_settings


@dataclass(frozen=True)
class Identity:
    """Who makes a request: the user name, the groups, and the access token itself.

    The graph passes `token` to the MCP servers. repr() leaves the token out, so it does not
    go to a log by mistake.
    """

    user: str
    groups: tuple[str, ...] = ()
    token: str = field(default="", repr=False)


_service: dict[str, float | str] = {}
_service_lock = threading.Lock()


def service_token() -> str:
    """An access token for a job that runs without a person (make testset, make agent-eval).

    The client `assistant-service` gets it with the client credentials grant. Its user is
    `service-account-assistant-service`, in the groups analysts and auditors. The token is kept
    until 30 seconds before it expires.
    """
    settings = get_settings()
    with _service_lock:
        if _service.get("token") and float(_service["expires"]) > time.time() + 30:
            return str(_service["token"])
        metadata = httpx.get(settings.auth_metadata_url, timeout=10).raise_for_status().json()
        response = httpx.post(
            metadata["token_endpoint"],
            data={"grant_type": "client_credentials"},
            auth=(settings.auth_client_id, settings.auth_client_secret),
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        _service.update(token=body["access_token"], expires=time.time() + float(body.get("expires_in", 60)))
        return body["access_token"]


@lru_cache
def _keys(metadata_url: str, issuer: str) -> jwt.PyJWKClient:
    metadata = httpx.get(metadata_url, timeout=10).raise_for_status().json()
    if metadata["issuer"] != issuer:
        raise RuntimeError(f"Unexpected issuer: {metadata['issuer']} (AUTH_ISSUER is {issuer})")
    return jwt.PyJWKClient(metadata["jwks_uri"], timeout=5)


def claims_of(token: str, audience: str) -> dict[str, Any] | None:
    """The claims of a valid token for `audience`, or None."""
    settings = get_settings()
    if not token:
        return None
    try:
        key = _keys(settings.auth_metadata_url, settings.auth_issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=settings.auth_issuer, audience=audience,
                            leeway=30, options={"require": ["exp", "iss", "aud"]})
    except jwt.PyJWKClientConnectionError:
        raise  # An outage of the authorization server, not a bad token.
    except jwt.PyJWTError:
        return None
    scope = claims.get("scope")
    if settings.auth_scope not in (scope.split() if isinstance(scope, str) else []):
        return None
    if not claims.get("preferred_username"):
        return None
    return claims


def identity_of(claims: dict[str, Any], token: str) -> Identity:
    return Identity(user=claims["preferred_username"], groups=tuple(claims.get("groups") or ()), token=token)


def verify(token: str, audience: str) -> Identity | None:
    """The identity of a valid access token for `audience`, or None when the token is not valid."""
    claims = claims_of(token, audience)
    return identity_of(claims, token) if claims else None


def service_identity() -> Identity:
    """The identity of a job that runs without a person."""
    settings = get_settings()
    identity = verify(service_token(), settings.api_audience)
    if identity is None:
        raise RuntimeError("The service token is not valid for the API. Check the client assistant-service.")
    return identity


# ---- the MCP servers --------------------------------------------------------------------------


class McpTokenVerifier:
    """The TokenVerifier of an MCP server, as in the MCP authorization tutorial."""

    def __init__(self, audience: str, resource: str) -> None:
        self.audience, self.resource = audience, resource

    async def verify_token(self, token: str) -> AccessToken | None:
        import asyncio

        # PyJWKClient blocks while it fetches keys, so keep it off the event loop.
        claims = await asyncio.to_thread(claims_of, token, self.audience)
        if claims is None:
            return None
        scope = claims.get("scope")
        return AccessToken(
            token=token,
            client_id=claims.get("azp") or "",
            scopes=scope.split() if isinstance(scope, str) else [],
            expires_at=int(claims["exp"]),
            # claims_of has checked that the audience of the token is this server.
            resource=self.resource,
            subject=claims.get("sub"),
            claims=claims,
        )


def mcp_auth(audience: str, port: int) -> dict[str, Any]:
    """The arguments token_verifier and auth of FastMCP for a server with this audience."""
    import os

    settings = get_settings()
    resource = os.environ.get("MCP_RESOURCE_URL", f"http://localhost:{port}/mcp")
    return {
        "token_verifier": McpTokenVerifier(audience, resource),
        # model_validate keeps the issuer as it is: the issuer is compared character by character.
        "auth": AuthSettings.model_validate({
            "issuer_url": settings.auth_issuer,
            "resource_server_url": resource,
            "required_scopes": [settings.auth_scope],
            "validate_token_resource": True,
        }),
    }


def caller() -> Identity:
    """The identity of the request that a tool of an MCP server serves."""
    from mcp.server.auth.middleware.auth_context import get_access_token

    access = get_access_token()
    if access is None or not access.claims:
        raise PermissionError("No signed-in user.")
    return identity_of(access.claims, access.token)
