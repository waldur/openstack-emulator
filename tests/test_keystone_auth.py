"""Tests for Keystone token authorization: roles, privilege and auth methods."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple


@pytest.fixture
def client():
    """Create a test client."""
    apps = create_all_service_apps()
    return TestClient(apps["keystone"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset keystone state between tests."""
    db.reset_keystone()
    yield


def _password_auth(client, user_name, project_name=None, project_id=None):
    """Authenticate with a password, optionally scoping to a project."""
    body = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": user_name,
                        "domain": {"id": "default"},
                        "password": "s4l4dus",
                    }
                },
            }
        }
    }
    if project_id:
        body["auth"]["scope"] = {"project": {"id": project_id}}
    elif project_name:
        body["auth"]["scope"] = {"project": {"name": project_name, "domain": {"id": "default"}}}
    return client.post("/v3/auth/tokens", json=body)


class TestTokenPrivilege:
    """A token is privileged only via the admin project or a real admin role."""

    def test_admin_project_token_is_privileged(self, client):
        response = _password_auth(client, "admin", project_name="admin")
        assert response.status_code == 200
        info = validate_token_simple(response.headers["X-Subject-Token"])
        assert info.is_admin is True

    def test_member_project_token_is_not_privileged(self, client):
        project = db.create_project(name="tenant-a", domain_id="default")
        db.create_user(name="alice", domain_id="default")

        response = _password_auth(client, "alice", project_id=project.id)
        assert response.status_code == 200
        info = validate_token_simple(response.headers["X-Subject-Token"])
        assert info.is_admin is False

    def test_real_admin_role_assignment_confers_privilege(self, client):
        project = db.create_project(name="tenant-b", domain_id="default")
        user = db.create_user(name="bob", domain_id="default")
        role = db.create_role(name="admin")
        db.assign_role_to_user_on_project(role.id, user.id, project.id)

        response = _password_auth(client, "bob", project_id=project.id)
        assert response.status_code == 200
        info = validate_token_simple(response.headers["X-Subject-Token"])
        assert info.is_admin is True

    def test_default_role_fallback_does_not_confer_privilege(self, client):
        """A user with no assignments still gets a usable token, not an admin one."""
        project = db.create_project(name="tenant-c", domain_id="default")
        db.create_user(name="carol", domain_id="default")

        response = _password_auth(client, "carol", project_id=project.id)
        body = response.json()
        # The convenience fallback still hands out a role so the token is usable...
        assert [role["name"] for role in body["token"]["roles"]] == ["admin"]
        # ...but it must not be mistaken for genuine privilege.
        assert validate_token_simple(response.headers["X-Subject-Token"]).is_admin is False


class TestTokenRescoping:
    """Rescoping preserves the exact user rather than re-resolving by name."""

    def test_rescope_preserves_user_id(self, client):
        project = db.create_project(name="tenant-d", domain_id="default")
        user = db.create_user(name="dave", domain_id="default")

        first = _password_auth(client, "dave", project_id=project.id)
        unscoped_id = first.headers["X-Subject-Token"]

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {"methods": ["token"], "token": {"id": unscoped_id}},
                    "scope": {"project": {"id": project.id}},
                }
            },
        )
        assert response.status_code == 200
        assert response.json()["token"]["user"]["id"] == user.id
        assert response.json()["token"]["methods"] == ["token"]


class TestApplicationCredentialAuth:
    """Application credentials authenticate and carry their own fixed scope."""

    def _create_cred(self, roles=None):
        project = db.create_project(name="tenant-e", domain_id="default")
        user = db.create_user(name="erin", domain_id="default")
        cred = db.create_application_credential(
            user_id=user.id,
            name="deploy-bot",
            project_id=project.id,
            roles=roles if roles is not None else [{"id": "member-id", "name": "member"}],
        )
        return project, user, cred

    def test_authenticates_and_scopes_to_the_credential_project(self, client):
        project, user, cred = self._create_cred()

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {"id": cred.id, "secret": cred.secret},
                    }
                }
            },
        )
        assert response.status_code == 200
        body = response.json()["token"]
        assert body["project"]["id"] == project.id
        assert body["user"]["id"] == user.id
        assert [role["name"] for role in body["roles"]] == ["member"]

    def test_scope_in_the_request_cannot_widen_the_credential(self, client):
        project, _user, cred = self._create_cred()
        other = db.create_project(name="admin", domain_id="default")

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {"id": cred.id, "secret": cred.secret},
                    },
                    "scope": {"project": {"id": other.id}},
                }
            },
        )
        assert response.status_code == 200
        assert response.json()["token"]["project"]["id"] == project.id
        assert validate_token_simple(response.headers["X-Subject-Token"]).is_admin is False

    def test_wrong_secret_is_rejected(self, client):
        _project, _user, cred = self._create_cred()

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {"id": cred.id, "secret": "wrong"},
                    }
                }
            },
        )
        assert response.status_code == 401

    def test_unknown_credential_is_rejected(self, client):
        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {"id": "nope", "secret": "nope"},
                    }
                }
            },
        )
        assert response.status_code == 401

    def test_credential_with_admin_role_is_privileged(self, client):
        _project, _user, cred = self._create_cred(roles=[{"id": "admin-id", "name": "admin"}])

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {"id": cred.id, "secret": cred.secret},
                    }
                }
            },
        )
        assert validate_token_simple(response.headers["X-Subject-Token"]).is_admin is True


class TestUnscopedTokens:
    """Unscoped tokens carry neither a project nor a catalog."""

    def test_unscoped_token_omits_project_and_catalog(self):
        db.create_user(name="frank", domain_id="default")
        token = db.create_token(user_name="frank", unscoped=True)
        body = token.to_dict()["token"]

        assert "project" not in body
        assert "catalog" not in body
        assert body["user"]["name"] == "frank"
        assert token.is_admin is False
