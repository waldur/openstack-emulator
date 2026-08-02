"""Tests for the embedded OpenID Provider."""

import base64

import jwt
import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture
def client():
    """OpenID Provider test client."""
    return TestClient(create_all_service_apps()["oidc"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset provider state between tests."""
    db.reset_oidc()
    yield


@pytest.fixture
def registered():
    """A confidential client and one end user."""
    db.create_oidc_client(client_id="waldur", client_secret="secret")
    return db.create_oidc_user(
        username="alice",
        password="pw",
        email="alice@example.org",
        name="Alice",
        groups=["hpc-users"],
        claims={"eduperson_entitlement": "urn:mace:example.org:hpc"},
    )


def _password_grant(client, **overrides):
    data = {
        "grant_type": "password",
        "username": "alice",
        "password": "pw",
        "client_id": "waldur",
        "client_secret": "secret",
    }
    data.update(overrides)
    return client.post("/token", data=data)


class TestDiscovery:
    """The discovery document keystoneauth reads before anything else."""

    def test_advertises_the_endpoints_and_grants(self, client):
        body = client.get("/.well-known/openid-configuration").json()

        assert body["token_endpoint"].endswith("/token")
        assert body["jwks_uri"].endswith("/keys")
        assert "password" in body["grant_types_supported"]
        assert "client_credentials" in body["grant_types_supported"]
        assert body["id_token_signing_alg_values_supported"] == ["RS256"]

    def test_issuer_follows_the_request_host(self, client):
        body = client.get("/.well-known/openid-configuration").json()
        assert body["issuer"] == body["token_endpoint"].removesuffix("/token")

    def test_jwks_publishes_an_rsa_key(self, client):
        body = client.get("/keys").json()

        key = body["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["n"] and key["e"]


class TestPasswordGrant:
    """The grant keystoneauth's v3oidcpassword plugin uses."""

    def test_issues_a_signed_token_with_the_user_claims(self, client, registered):
        response = _password_grant(client)
        assert response.status_code == 200

        body = response.json()
        assert body["token_type"] == "Bearer"
        claims = jwt.decode(body["access_token"], options={"verify_signature": False})
        assert claims["sub"] == registered.subject
        assert claims["email"] == "alice@example.org"
        assert claims["preferred_username"] == "alice"
        assert claims["groups"] == ["hpc-users"]
        assert claims["eduperson_entitlement"] == "urn:mace:example.org:hpc"

    def test_token_verifies_against_the_published_key(self, client, registered):
        access_token = _password_grant(client).json()["access_token"]
        from emulator.api.oidc import decode_access_token

        assert decode_access_token(access_token)["sub"] == registered.subject

    def test_wrong_password_is_invalid_grant(self, client, registered):
        response = _password_grant(client, password="nope")

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_grant"

    def test_unknown_user_is_invalid_grant(self, client, registered):
        response = _password_grant(client, username="nobody")
        assert response.json()["error"] == "invalid_grant"

    def test_unknown_client_is_rejected(self, client, registered):
        response = _password_grant(client, client_id="stranger")
        assert response.status_code == 401

    def test_wrong_client_secret_is_rejected(self, client, registered):
        response = _password_grant(client, client_secret="wrong")
        assert response.status_code == 401

    def test_http_basic_client_auth_is_accepted(self, client, registered):
        credentials = base64.b64encode(b"waldur:secret").decode()
        response = client.post(
            "/token",
            data={"grant_type": "password", "username": "alice", "password": "pw"},
            headers={"Authorization": f"Basic {credentials}"},
        )
        assert response.status_code == 200

    def test_unsupported_grant_type(self, client, registered):
        response = _password_grant(client, grant_type="magic")
        assert response.status_code == 400
        assert response.json()["error"] == "unsupported_grant_type"


class TestOtherGrants:
    """Client credentials, authorization code and refresh token."""

    def test_client_credentials(self, client, registered):
        response = client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "waldur",
                "client_secret": "secret",
            },
        )
        assert response.status_code == 200
        claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
        assert claims["sub"] == "waldur"

    def test_authorization_code(self, client, registered):
        authorize = client.get(
            "/authorize",
            params={
                "client_id": "waldur",
                "redirect_uri": "https://app.example.org/cb",
                "username": "alice",
                "state": "xyz",
            },
            follow_redirects=False,
        )
        assert authorize.status_code == 302
        location = authorize.headers["location"]
        assert "state=xyz" in location
        code = location.split("code=")[1].split("&")[0]

        response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://app.example.org/cb",
                "client_id": "waldur",
                "client_secret": "secret",
            },
        )
        assert response.status_code == 200

    def test_authorization_code_is_single_use(self, client, registered):
        authorize = client.get(
            "/authorize",
            params={
                "client_id": "waldur",
                "redirect_uri": "https://app.example.org/cb",
                "username": "alice",
            },
            follow_redirects=False,
        )
        code = authorize.headers["location"].split("code=")[1].split("&")[0]
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://app.example.org/cb",
            "client_id": "waldur",
            "client_secret": "secret",
        }

        assert client.post("/token", data=data).status_code == 200
        assert client.post("/token", data=data).json()["error"] == "invalid_grant"

    def test_authorize_rejects_an_unknown_user(self, client, registered):
        response = client.get(
            "/authorize",
            params={
                "client_id": "waldur",
                "redirect_uri": "https://app.example.org/cb",
                "username": "nobody",
            },
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_refresh_token(self, client, registered):
        first = _password_grant(client).json()

        response = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": first["refresh_token"],
                "client_id": "waldur",
                "client_secret": "secret",
            },
        )
        assert response.status_code == 200
        claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
        assert claims["sub"] == registered.subject


class TestUserinfoAndIntrospection:
    """Reading a token back."""

    def test_userinfo(self, client, registered):
        access_token = _password_grant(client).json()["access_token"]

        response = client.get("/userinfo", headers={"Authorization": f"Bearer {access_token}"})
        assert response.status_code == 200
        assert response.json()["email"] == "alice@example.org"

    def test_userinfo_without_a_token(self, client, registered):
        assert client.get("/userinfo").status_code == 401

    def test_userinfo_with_a_bad_token(self, client, registered):
        response = client.get("/userinfo", headers={"Authorization": "Bearer nope"})
        assert response.status_code == 401

    def test_introspection_of_a_live_token(self, client, registered):
        access_token = _password_grant(client).json()["access_token"]

        response = client.post(
            "/introspect",
            data={"token": access_token, "client_id": "waldur", "client_secret": "secret"},
        )
        body = response.json()
        assert body["active"] is True
        assert body["sub"] == registered.subject

    def test_introspection_of_an_unknown_token_is_inactive_not_an_error(self, client, registered):
        response = client.post(
            "/introspect",
            data={"token": "garbage", "client_id": "waldur", "client_secret": "secret"},
        )
        assert response.status_code == 200
        assert response.json() == {"active": False}
