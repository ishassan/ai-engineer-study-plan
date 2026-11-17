"""Sign-in: the identity of a request, from an access token of Keycloak. Phase 5, week 19.

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

import httpx

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


def verify(token: str, audience: str) -> Identity | None:
    """The identity of a valid access token for `audience`, or None when the token is not valid.

    A valid token has a good signature (a key of the `jwks_uri` of the metadata at
    AUTH_METADATA_URL), the issuer AUTH_ISSUER, the audience `audience`, a time of expiry that
    has not passed, and the scope AUTH_SCOPE (mcp:tools) in its claim `scope`. The user is the
    claim preferred_username, the groups are the claim groups.

    Raise an exception when the signing keys cannot be fetched: that is an outage of the
    authorization server, not a bad token.
    """
    raise NotImplementedError("Week 19, step 2")
