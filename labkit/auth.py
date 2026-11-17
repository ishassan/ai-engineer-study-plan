"""Sign-in for the lab: the three test users, a token client, and a fake authorization server.

From Phase 5 the API and the two MCP servers accept a request only with an access token of
the authorization server. In Docker that server is Keycloak (realm `lab`, see
keycloak/realm-lab.json). The offline checks do not need Keycloak: the plugin starts the
fake server of this module and points AUTH_ISSUER, AUTH_METADATA_URL and AUTH_TOKEN_URL at
it. It has the endpoints of a Keycloak realm that the lab uses (OpenID Connect discovery,
the signing keys, and the token endpoint with the password grant) and gives tokens with the
same claims as the realm.

A check can also make a token directly with `mint()`, for any user name, and make tokens
that must be refused: expired, signed with another key, for another audience, without the
scope.

The checks of Phases 1 to 4 send no token. While the fake server runs, the `client` fixture of
the plugin adds one to each request that has no Authorization header: a token for the user of
the header X-User (or `anonymous`), who may read everything. So these checks keep their meaning
when the API needs a token.
"""

from __future__ import annotations

import base64
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

REALM = "lab"
# The client of the lab scripts and the attack suite (a public client with the password grant).
CLIENT_ID = "assistant-cli"
# The client of the jobs that run without a person (the evaluations): the client credentials
# grant. Its token is for the user SERVICE_USER, who may read everything.
SERVICE_CLIENT_ID = "assistant-service"
SERVICE_CLIENT_SECRET = "assistant-service-secret"
SERVICE_USER = f"service-account-{SERVICE_CLIENT_ID}"
# The audience of each token: the API and the two MCP servers. Each one checks its own.
AUDIENCES = ("assistant-api", "mcp-sql", "mcp-catalogue")
SCOPE = "openid profile mcp:tools"
# The three users of the realm. The passwords are for a server that only your machine reaches.
TEST_USERS: dict[str, dict[str, Any]] = {
    "viewer": {"password": "viewer-password", "groups": []},
    "analyst": {"password": "analyst-password", "groups": ["analysts"]},
    "auditor": {"password": "auditor-password", "groups": ["auditors"]},
}
# The groups of a user of the earlier checks (any user name): it may read everything.
CHECK_GROUPS = ["analysts", "auditors"]
DEFAULT_TOKEN_URL = f"http://localhost:8180/realms/{REALM}/protocol/openid-connect/token"


def password_token(user: str, password: str | None = None, token_url: str | None = None) -> str:
    """Get an access token for a test user with the password grant. Used by scripts/get_token.py."""
    issuer = os.environ.get("AUTH_ISSUER", "").rstrip("/")
    url = token_url or os.environ.get("AUTH_TOKEN_URL") or (
        f"{issuer}/protocol/openid-connect/token" if issuer else DEFAULT_TOKEN_URL)
    if password is None:
        if user not in TEST_USERS:
            raise KeyError(f"{user!r} is not a test user. The test users are: {', '.join(TEST_USERS)}.")
        password = TEST_USERS[user]["password"]
    form = {"grant_type": "password", "client_id": CLIENT_ID, "username": user, "password": password,
            "scope": "openid mcp:tools"}
    response = httpx.post(url, data=form, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"The token endpoint {url} answered {response.status_code}: {response.text[:300]}")
    return response.json()["access_token"]


# ---- the fake authorization server --------------------------------------------------------------


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": _b64(numbers.n), "e": _b64(numbers.e)}


class FakeAuth:
    """The state of the fake server: the signing key and the issuer URL."""

    def __init__(self, key: rsa.RSAPrivateKey, base_url: str) -> None:
        self.key, self.kid = key, "lab-fake-key"
        self.base_url = base_url
        self.issuer = f"{base_url}/realms/{REALM}"
        self.token_requests: list[dict[str, str]] = []

    def metadata(self) -> dict[str, Any]:
        oidc = f"{self.issuer}/protocol/openid-connect"
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{oidc}/auth",
            "token_endpoint": f"{oidc}/token",
            "jwks_uri": f"{oidc}/certs",
            "grant_types_supported": ["authorization_code", "password", "refresh_token"],
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "scopes_supported": ["openid", "profile", "mcp:tools"],
        }

    def mint(
        self,
        user: str,
        groups: list[str] | None = None,
        *,
        audience: tuple[str, ...] | list[str] | str = AUDIENCES,
        expires_in: int = 600,
        scope: str = SCOPE,
        issuer: str | None = None,
        key: rsa.RSAPrivateKey | None = None,
        azp: str = CLIENT_ID,
    ) -> str:
        """A signed access token with the claims of a token of the realm."""
        now = int(time.time())
        if groups is None:
            groups = TEST_USERS[user]["groups"] if user in TEST_USERS else CHECK_GROUPS
        claims = {
            "exp": now + expires_in,
            "iat": now - 1,
            "jti": str(uuid.uuid4()),
            "iss": issuer or self.issuer,
            "aud": list(audience) if not isinstance(audience, str) else audience,
            "sub": str(uuid.uuid5(uuid.NAMESPACE_URL, f"lab-user:{user}")),
            "typ": "Bearer",
            "azp": azp,
            "scope": scope,
            "preferred_username": user,
        }
        if groups:  # Keycloak leaves the claim out for a user without a group.
            claims["groups"] = list(groups)
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": self.kid})

    def app(self) -> Starlette:
        async def discovery(request: Request) -> JSONResponse:
            return JSONResponse(self.metadata())

        async def certs(request: Request) -> JSONResponse:
            return JSONResponse({"keys": [_jwk(self.key, self.kid)]})

        async def token(request: Request) -> JSONResponse:
            form = dict(await request.form())
            self.token_requests.append(form)
            if form.get("grant_type") == "client_credentials":
                client_id, secret = form.get("client_id", ""), form.get("client_secret", "")
                basic = request.headers.get("authorization", "")
                if basic.lower().startswith("basic "):
                    client_id, _, secret = base64.b64decode(basic[6:]).decode().partition(":")
                if (client_id, secret) != (SERVICE_CLIENT_ID, SERVICE_CLIENT_SECRET):
                    return JSONResponse({"error": "unauthorized_client"}, status_code=401)
                access = self.mint(SERVICE_USER, CHECK_GROUPS, azp=SERVICE_CLIENT_ID)
                return JSONResponse({"access_token": access, "expires_in": 600, "token_type": "Bearer", "scope": SCOPE})
            user, password = form.get("username", ""), form.get("password", "")
            if form.get("grant_type") != "password" or form.get("client_id") != CLIENT_ID:
                return JSONResponse({"error": "unauthorized_client"}, status_code=400)
            if user not in TEST_USERS or TEST_USERS[user]["password"] != password:
                return JSONResponse({"error": "invalid_grant", "error_description": "Invalid user credentials"}, status_code=400)
            access = self.mint(user)
            return JSONResponse({"access_token": access, "expires_in": 600, "token_type": "Bearer", "scope": SCOPE})

        prefix = f"/realms/{REALM}"
        return Starlette(routes=[
            Route(f"{prefix}/.well-known/openid-configuration", discovery),
            Route(f"/.well-known/oauth-authorization-server{prefix}", discovery),
            Route(f"{prefix}/protocol/openid-connect/certs", certs),
            Route(f"{prefix}/protocol/openid-connect/token", token, methods=["POST"]),
        ])


class FakeAuthServer:
    """Run a FakeAuth on a free localhost port, in a background thread.

    A check that starts pytest again in a new process (for example the trace checks) must use
    the same server, because the MCP servers of the first process trust only its key. So the
    first process writes the key to a file and sets LAB_FAKE_AUTH_URL and LAB_FAKE_AUTH_KEY;
    a later process that finds both reuses that server and does not start one.
    """

    def __init__(self, folder: Path) -> None:
        self._server: uvicorn.Server | None = None
        url, key_file = os.environ.get("LAB_FAKE_AUTH_URL"), os.environ.get("LAB_FAKE_AUTH_KEY")
        if url and key_file and Path(key_file).exists() and _answers(url):
            key = serialization.load_pem_private_key(Path(key_file).read_bytes(), password=None)
            self.auth = FakeAuth(key, url)
            return
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.auth = FakeAuth(new_key(), f"http://127.0.0.1:{port}")
        key_path = folder / "fake-auth-key.pem"
        key_path.write_bytes(self.auth.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.environ.update(LAB_FAKE_AUTH_URL=self.auth.base_url, LAB_FAKE_AUTH_KEY=str(key_path))
        config = uvicorn.Config(self.auth.app(), host="127.0.0.1", port=port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> FakeAuth:
        if self._server is not None:
            self._thread.start()
            deadline = time.monotonic() + 10
            while not self._server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("The fake authorization server did not start.")
                time.sleep(0.02)
        return self.auth

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
            self._thread.join(timeout=5)


def _answers(url: str) -> bool:
    try:
        return httpx.get(f"{url}/realms/{REALM}/.well-known/openid-configuration", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


# ---- tokens for the checks of the earlier phases -------------------------------------------------

# The fake server of this test run. The plugin sets it when it starts the server.
FAKE: FakeAuth | None = None


def check_headers(user: str = "anonymous") -> dict[str, str]:
    """An Authorization header for a user of the checks, or {} when no fake server runs."""
    if FAKE is None:
        return {}
    return {"Authorization": f"Bearer {FAKE.mint(user)}"}


class SignedIn:
    """A mixin for an httpx client (also the TestClient of Starlette).

    A request without an Authorization header gets a token for the user of its X-User header,
    or for `anonymous`. A request that has an Authorization header, also an empty one, is sent
    as it is: the checks of week 19 use this to send no token or a bad one.
    """

    def request(self, method: str, url: Any, *args: Any, headers: Any = None, **kwargs: Any) -> Any:
        names = {name.lower() for name in (headers or {})}
        if FAKE is not None and "authorization" not in names:
            user = next((value for name, value in dict(headers or {}).items() if name.lower() == "x-user"), "")
            headers = {**dict(headers or {}), **check_headers(user.strip() or "anonymous")}
        return super().request(method, url, *args, headers=headers, **kwargs)


class SignedInClient(SignedIn, httpx.Client):
    """An httpx.Client that signs in each request of a check."""
