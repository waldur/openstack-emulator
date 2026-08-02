"""Tests for Keystone token authorization: roles, privilege and auth methods."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple
from tests.conftest import grant_scope


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
        project = grant_scope(project_name="tenant-a", user_name="alice")

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

    def test_a_user_with_no_assignment_is_refused(self, client):
        """Keystone will not mint a scoped token that would carry no roles."""
        project = db.create_project(name="tenant-c", domain_id="default")
        db.create_user(name="carol", domain_id="default")

        response = _password_auth(client, "carol", project_id=project.id)

        assert response.status_code == 401
        assert "no access to project" in response.json()["error"]["message"]


class TestTokenRescoping:
    """Rescoping preserves the exact user rather than re-resolving by name."""

    def test_rescope_preserves_user_id(self, client):
        project = grant_scope(project_name="tenant-d", user_name="dave")
        user = db.get_user_by_name("dave", "default")

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


class TestScopeRequiresAssignment:
    """Keystone's scoping rule, reproduced.

    ``TokenModel.mint`` runs ``_validate_project_scope``, which raises
    ``Unauthorized`` when a project-scoped token would carry no roles. There is
    no default-role fallback in Keystone and there is none here.
    """

    def test_direct_assignment_is_enough(self, client):
        project = db.create_project(name="direct", domain_id="default")
        user = db.create_user(name="dana", domain_id="default")
        role = db.create_role(name="member")
        db.assign_role_to_user_on_project(role.id, user.id, project.id)

        response = _password_auth(client, "dana", project_id=project.id)

        assert response.status_code == 200
        assert [r["name"] for r in response.json()["token"]["roles"]] == ["member"]

    def test_a_group_assignment_is_enough(self, client):
        """Group-derived roles count, as they do in Keystone's role resolution."""
        project = db.create_project(name="via-group", domain_id="default")
        user = db.create_user(name="gina", domain_id="default")
        group = db.create_group(name="engineers", domain_id="default")
        db.add_user_to_group(user.id, group.id)
        role = db.create_role(name="member")
        db.assign_role_to_group_on_project(role.id, group.id, project.id)

        response = _password_auth(client, "gina", project_id=project.id)

        assert response.status_code == 200
        assert [r["name"] for r in response.json()["token"]["roles"]] == ["member"]

    def test_an_unscoped_token_needs_no_assignment(self, client):
        """Only *scoped* tokens are checked; an unscoped one proves identity only."""
        db.create_user(name="hal", domain_id="default")

        token = db.create_token(user_name="hal", unscoped=True)

        assert token.roles == []
        assert token.is_admin is False

    def test_an_unknown_name_is_not_the_admin_user(self, client):
        """An unrecognised name must not inherit the seeded admin's assignments.

        It used to resolve to the default user id, which is the admin's, so any
        name at all could scope wherever the admin could.
        """
        admin = db.get_user_by_name("admin", "default")

        token = db.create_token(user_name="not-a-real-account", unscoped=True)

        assert token.user_id != admin.id

    def test_the_same_unknown_name_is_a_stable_identity(self, client):
        first = db.create_token(user_name="ghost", unscoped=True)
        second = db.create_token(user_name="ghost", unscoped=True)

        assert first.user_id == second.user_id
