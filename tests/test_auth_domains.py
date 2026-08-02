"""Password auth must honour domains named by name, for user and project alike.

A client names a domain by ``id`` *or* by ``name``. The auth handler defaulted
the id before consulting the name, so the name branch was dead and every user
outside ``default`` was unreachable: the lookup missed, an unknown-user identity
was synthesised, and the scope fell back to the default project — the *admin*
project. Keystone also treats a user's domain and a scoped project's domain as
independent, so a project name has to be resolved in its own domain.

Surfaced by a two-tenant RBAC scenario, where both projects live in a dedicated
domain.
"""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import grant_scope

DOMAIN = "tenants"
PROJECT = "tenant-a"
USER = "alice@example.org"
PASSWORD = "pw"


@pytest.fixture
def client():
    return TestClient(create_all_service_apps()["keystone"])


@pytest.fixture(autouse=True)
def seeded():
    """A user and a project in a domain that is not ``default``."""
    db.reset_keystone()
    domain = db.create_domain(name=DOMAIN)
    project = grant_scope(project_name=PROJECT, user_name=USER, domain_id=domain.id)
    user = db.get_user_by_name(USER, domain.id)
    user.password = PASSWORD
    return domain, project, user


def auth(client, body):
    return client.post("/v3/auth/tokens", json={"auth": body})


def password_body(user_domain, project_domain=None, project_name=PROJECT):
    scope_project = {"name": project_name}
    if project_domain is not None:
        scope_project["domain"] = project_domain
    return {
        "identity": {
            "methods": ["password"],
            "password": {"user": {"name": USER, "domain": user_domain, "password": PASSWORD}},
        },
        "scope": {"project": scope_project},
    }


class TestDomainByName:
    """The domain named by ``name`` must resolve."""

    def test_login_succeeds(self, client, seeded):
        response = auth(client, password_body({"name": DOMAIN}, {"name": DOMAIN}))

        assert response.status_code == 200, response.text

    def test_token_names_the_right_user(self, client, seeded):
        _, _, user = seeded

        response = auth(client, password_body({"name": DOMAIN}, {"name": DOMAIN}))

        assert response.json()["token"]["user"]["id"] == user.id

    def test_token_scopes_to_the_right_project(self, client, seeded):
        _, project, _ = seeded

        response = auth(client, password_body({"name": DOMAIN}, {"name": DOMAIN}))

        assert response.json()["token"]["project"]["id"] == project.id

    def test_it_does_not_fall_back_to_the_admin_project(self, client, seeded):
        """The failure mode: an unknown user scoped at the default project."""
        response = auth(client, password_body({"name": DOMAIN}, {"name": DOMAIN}))

        assert response.json()["token"]["project"]["name"] != "admin"

    def test_domain_by_id_still_works(self, client, seeded):
        domain, project, _ = seeded

        response = auth(client, password_body({"id": domain.id}, {"id": domain.id}))

        assert response.status_code == 200
        assert response.json()["token"]["project"]["id"] == project.id


class TestIndependentProjectDomain:
    """A project's domain is not necessarily the user's."""

    def test_project_resolves_in_its_own_domain(self, client, seeded):
        """A same-named project in `default` must not win over the real one."""
        domain, project, _ = seeded
        db.create_project(name=PROJECT, domain_id="default")

        response = auth(client, password_body({"name": DOMAIN}, {"name": DOMAIN}))

        assert response.json()["token"]["project"]["id"] == project.id


class TestDefaultDomainUnaffected:
    def test_admin_still_authenticates(self, client):
        response = auth(
            client,
            {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "admin",
                            "domain": {"id": "default"},
                            "password": "s4l4dus",
                        }
                    },
                },
                "scope": {"project": {"name": "admin"}},
            },
        )

        assert response.status_code == 200
