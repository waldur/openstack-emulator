"""Embedded OpenID Provider for the OpenStack emulator.

Keystone federation needs somewhere to get an access token from. Rather than
require an external identity provider for every federation test, the emulator
ships a minimal but real OpenID Provider: it publishes a discovery document and
a JWKS, and issues RS256-signed access tokens through the password,
client_credentials, authorization_code and refresh_token grants.

The signing key is generated at process start. It is never persisted, so tokens
do not survive a restart — which is correct for an emulator and avoids shipping
a private key in the repository.

Keystone's side of the exchange lives in :mod:`emulator.api.keystone`; see
``emulator/core/federation.py`` for the mapping engine that turns the claims in
these tokens into a Keystone identity.
"""

import base64
import logging
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Form, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from emulator.core.database import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oidc"])

#: How long an issued access token is valid, in seconds.
TOKEN_LIFETIME = 3600

_SUPPORTED_GRANTS = [
    "password",
    "client_credentials",
    "authorization_code",
    "refresh_token",
]


class _SigningKey:
    """The provider's RSA signing key, generated once per process."""

    def __init__(self) -> None:
        self._private_key: rsa.RSAPrivateKey | None = None
        self.kid = "emulator-oidc-key-1"

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        """Generate the key on first use so import stays cheap."""
        if self._private_key is None:
            self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return self._private_key

    def private_pem(self) -> bytes:
        """The private key in PEM form, for signing."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_pem(self) -> bytes:
        """The public key in PEM form, for verification."""
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def jwk(self) -> dict[str, Any]:
        """The public key as a JWK, for the JWKS endpoint."""
        numbers = self.private_key.public_key().public_numbers()

        def _b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": _b64(numbers.n),
            "e": _b64(numbers.e),
        }


signing_key = _SigningKey()


def issuer_url(request: Request) -> str:
    """The issuer identifier, derived from the incoming request.

    Deriving it per request rather than pinning it in configuration keeps the
    emulator usable behind any host or port, including the ephemeral ports the
    SDK test fixtures bind.
    """
    return str(request.base_url).rstrip("/")


def issue_access_token(
    request: Request, subject: str, audience: str, claims: dict[str, Any]
) -> str:
    """Sign an RS256 access token carrying the given claims."""
    now = int(time.time())
    payload = {
        **claims,
        "iss": issuer_url(request),
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + TOKEN_LIFETIME,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        signing_key.private_pem(),
        algorithm="RS256",
        headers={"kid": signing_key.kid},
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and decode a token this provider issued.

    Raises :class:`jwt.PyJWTError` if the signature, expiry or format is wrong.
    Audience is not checked here: the relying party that presents the token
    (Keystone) is not the audience the token was minted for.
    """
    decoded: dict[str, Any] = jwt.decode(
        token,
        signing_key.public_pem(),
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    return decoded


def _authenticate_client(request: Request, client_id: str | None, client_secret: str | None) -> str:
    """Resolve the relying party from Basic auth or the form body.

    keystoneauth sends HTTP Basic when a client secret is configured and falls
    back to ``client_id`` in the body otherwise, so both are accepted.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
            client_id, client_secret = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=401, detail="invalid_client") from exc

    if not client_id:
        raise HTTPException(status_code=401, detail="invalid_client")

    client = db.get_oidc_client(client_id)
    if client is None:
        raise HTTPException(status_code=401, detail="invalid_client")
    if client.client_secret and client.client_secret != (client_secret or ""):
        raise HTTPException(status_code=401, detail="invalid_client")
    return client_id


@router.get("/.well-known/openid-configuration")
async def discovery(request: Request) -> dict[str, Any]:
    """Publish the OpenID Connect discovery document.

    keystoneauth reads ``token_endpoint`` from here and refuses to continue when
    its grant type is missing from ``grant_types_supported``.
    """
    issuer = issuer_url(request)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "introspection_endpoint": f"{issuer}/introspect",
        "jwks_uri": f"{issuer}/keys",
        "grant_types_supported": _SUPPORTED_GRANTS,
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "groups"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "claims_supported": [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "email",
            "name",
            "preferred_username",
            "groups",
        ],
    }


@router.get("/keys")
async def jwks() -> dict[str, Any]:
    """Publish the provider's public signing key."""
    return {"keys": [signing_key.jwk()]}


@router.post("/token")
async def token(
    request: Request,
    grant_type: str = Form(...),
    username: str | None = Form(None),
    password: str | None = Form(None),
    scope: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    refresh_token: str | None = Form(None),
) -> JSONResponse:
    """Exchange a grant for an access token."""
    if grant_type not in _SUPPORTED_GRANTS:
        return JSONResponse(status_code=400, content={"error": "unsupported_grant_type"})

    resolved_client = _authenticate_client(request, client_id, client_secret)

    if grant_type == "password":
        if not username:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        user = db.get_oidc_user(username)
        if user is None or (user.password and user.password != (password or "")):
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})

    elif grant_type == "client_credentials":
        # The client acts on its own behalf; the subject is the client itself.
        user = db.get_oidc_user(resolved_client)
        if user is None:
            user = db.create_oidc_user(username=resolved_client, subject=resolved_client)

    elif grant_type == "authorization_code":
        if not code:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        record = db.consume_oidc_code(code)
        if record is None or record.client_id != resolved_client:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        if redirect_uri and record.redirect_uri and redirect_uri != record.redirect_uri:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        user = db.get_oidc_user(record.username)
        if user is None:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        scope = scope or record.scope

    else:  # refresh_token
        if not refresh_token:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        try:
            claims = decode_access_token(refresh_token)
        except jwt.PyJWTError:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        found = db.get_oidc_user_by_subject(str(claims.get("sub", "")))
        if found is None:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        user = found

    issuer = issuer_url(request)
    claims = user.to_claims(issuer, resolved_client)
    access_token = issue_access_token(request, user.subject, resolved_client, claims)

    return JSONResponse(
        content={
            "access_token": access_token,
            "id_token": access_token,
            "refresh_token": access_token,
            "token_type": "Bearer",
            "expires_in": TOKEN_LIFETIME,
            "scope": scope or "openid profile",
        }
    )


@router.get("/authorize")
async def authorize(
    request: Request,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    scope: str = Query("openid profile"),
    state: str | None = Query(None),
    username: str | None = Query(None),
) -> Response:
    """Issue an authorization code and redirect back to the relying party.

    There is no login form: the end user is named by the ``username`` query
    parameter, which keeps the grant scriptable from a test.
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")
    if db.get_oidc_client(client_id) is None:
        raise HTTPException(status_code=401, detail="invalid_client")
    if not username or db.get_oidc_user(username) is None:
        raise HTTPException(status_code=400, detail="unknown user")

    record = db.create_oidc_code(client_id, username, redirect_uri, scope)
    params = {"code": record.code}
    if state:
        params["state"] = state
    return RedirectResponse(url=f"{redirect_uri}?{urlencode(params)}", status_code=302)


@router.get("/userinfo")
async def userinfo(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Return the claims of the user the bearer token was issued for."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid_token")
    try:
        claims = decode_access_token(authorization.split(" ", 1)[1])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid_token") from exc

    user = db.get_oidc_user_by_subject(str(claims.get("sub", "")))
    if user is None:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user.to_claims(issuer_url(request), str(claims.get("aud", "")))


@router.post("/introspect")
async def introspect(
    request: Request,
    token: str = Form(...),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
) -> dict[str, Any]:
    """RFC 7662 token introspection.

    An inactive token is reported as ``{"active": false}`` rather than an error,
    as the RFC requires.
    """
    _authenticate_client(request, client_id, client_secret)
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError:
        return {"active": False}
    return {"active": True, **claims}
