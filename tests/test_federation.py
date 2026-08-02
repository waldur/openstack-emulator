"""Tests for the Keystone federation mapping engine and OS-FEDERATION endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.federation import MappingError, process_rules

IDP = "keycloak"
PROTOCOL = "openid"


class TestMappingEngine:
    """The rule processor, exercised directly."""

    def test_direct_substitution(self):
        rules = [
            {
                "local": [{"user": {"name": "{0}", "email": "{1}"}}],
                "remote": [{"type": "preferred_username"}, {"type": "email"}],
            }
        ]
        result = process_rules(rules, {"preferred_username": "alice", "email": "a@example.org"})

        assert result["user"] == {"name": "alice", "email": "a@example.org"}

    def test_missing_attribute_makes_the_rule_inapplicable(self):
        rules = [
            {
                "local": [{"user": {"name": "{0}"}}],
                "remote": [{"type": "preferred_username"}, {"type": "email"}],
            }
        ]
        with pytest.raises(MappingError):
            process_rules(rules, {"preferred_username": "alice"})

    def test_any_one_of_gates_without_consuming_a_position(self):
        """A gating requirement must not shift what {0} refers to."""
        rules = [
            {
                "local": [{"user": {"name": "{0}"}}],
                "remote": [
                    {"type": "groups", "any_one_of": ["staff"]},
                    {"type": "email"},
                ],
            }
        ]
        result = process_rules(rules, {"groups": ["staff"], "email": "a@example.org"})
        assert result["user"]["name"] == "a@example.org"

    def test_any_one_of_that_does_not_match_drops_the_rule(self):
        rules = [
            {
                "local": [{"user": {"name": "{0}"}}],
                "remote": [
                    {"type": "groups", "any_one_of": ["staff"]},
                    {"type": "email"},
                ],
            }
        ]
        with pytest.raises(MappingError):
            process_rules(rules, {"groups": ["student"], "email": "a@example.org"})

    def test_not_any_of(self):
        rules = [
            {
                "local": [{"user": {"name": "{0}"}}],
                "remote": [
                    {"type": "groups", "not_any_of": ["banned"]},
                    {"type": "email"},
                ],
            }
        ]
        assert process_rules(rules, {"groups": ["ok"], "email": "a@x"})["user"]["name"] == "a@x"
        with pytest.raises(MappingError):
            process_rules(rules, {"groups": ["banned"], "email": "a@x"})

    def test_whitelist_filters_the_mapped_values(self):
        rules = [
            {
                "local": [{"groups": "{0}"}],
                "remote": [{"type": "groups", "whitelist": ["devs", "ops"]}],
            }
        ]
        result = process_rules(rules, {"groups": ["devs", "finance"]})
        assert [group["name"] for group in result["groups"]] == ["devs"]

    def test_blacklist_filters_the_mapped_values(self):
        rules = [
            {
                "local": [{"groups": "{0}"}],
                "remote": [{"type": "groups", "blacklist": ["finance"]}],
            }
        ]
        result = process_rules(rules, {"groups": ["devs", "finance"]})
        assert [group["name"] for group in result["groups"]] == ["devs"]

    def test_regex_matching(self):
        rules = [
            {
                "local": [{"user": {"name": "{0}"}}],
                "remote": [
                    {"type": "entitlement", "any_one_of": ["^urn:mace:.*:hpc$"], "regex": True},
                    {"type": "email"},
                ],
            }
        ]
        result = process_rules(rules, {"entitlement": ["urn:mace:example.org:hpc"], "email": "a@x"})
        assert result["user"]["name"] == "a@x"

    def test_semicolon_delimited_groups_expand(self):
        rules = [{"local": [{"groups": "{0}"}], "remote": [{"type": "groups"}]}]
        result = process_rules(rules, {"groups": "devs;ops"})
        assert sorted(group["name"] for group in result["groups"]) == ["devs", "ops"]

    def test_projects_are_carried_through(self):
        rules = [
            {
                "local": [{"projects": [{"name": "proj-{0}", "roles": [{"name": "member"}]}]}],
                "remote": [{"type": "preferred_username"}],
            }
        ]
        result = process_rules(rules, {"preferred_username": "alice"})
        assert result["projects"] == [{"name": "proj-alice", "roles": [{"name": "member"}]}]

    def test_placeholder_beyond_the_matches_is_an_error(self):
        rules = [{"local": [{"user": {"name": "{5}"}}], "remote": [{"type": "preferred_username"}]}]
        with pytest.raises(MappingError):
            process_rules(rules, {"preferred_username": "alice"})


@pytest.fixture
def apps():
    """Build the service apps once per test."""
    return create_all_service_apps()


@pytest.fixture
def client(apps):
    """Keystone test client."""
    return TestClient(apps["keystone"])


@pytest.fixture
def oidc_client(apps):
    """Embedded OpenID Provider test client."""
    return TestClient(apps["oidc"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset identity and provider state between tests."""
    db.reset_keystone()
    db.reset_oidc()
    yield


@pytest.fixture
def admin_headers(client):
    """Headers for a token scoped to the admin project."""
    response = client.post(
        "/v3/auth/tokens",
        json={
            "auth": {
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
            }
        },
    )
    return {"X-Auth-Token": response.headers["X-Subject-Token"]}


@pytest.fixture
def federation_setup(client, admin_headers):
    """An identity provider, a mapping keyed on email, and a protocol."""
    client.put(
        f"/v3/OS-FEDERATION/identity_providers/{IDP}",
        headers=admin_headers,
        json={"identity_provider": {"description": "Test IdP", "domain_id": "default"}},
    )
    client.put(
        "/v3/OS-FEDERATION/mappings/email-map",
        headers=admin_headers,
        json={
            "mapping": {
                "rules": [
                    {
                        "local": [{"user": {"name": "{0}", "type": "local"}}],
                        "remote": [{"type": "email"}],
                    }
                ]
            }
        },
    )
    client.put(
        f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}",
        headers=admin_headers,
        json={"protocol": {"mapping_id": "email-map"}},
    )


def _access_token(oidc_client, username, email, groups=None):
    """Register a client and user with the embedded provider, then get a token."""
    db.create_oidc_client(client_id="waldur", client_secret="secret")
    db.create_oidc_user(username=username, password="pw", email=email, groups=list(groups or []))
    response = oidc_client.post(
        "/token",
        data={
            "grant_type": "password",
            "username": username,
            "password": "pw",
            "client_id": "waldur",
            "client_secret": "secret",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


class TestProtocolEndpoints:
    """Protocol CRUD under an identity provider."""

    def test_crud(self, client, admin_headers, federation_setup):
        listed = client.get(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols", headers=admin_headers
        )
        assert [p["id"] for p in listed.json()["protocols"]] == [PROTOCOL]

        fetched = client.get(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}",
            headers=admin_headers,
        )
        assert fetched.json()["protocol"]["mapping_id"] == "email-map"

        deleted = client.delete(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}",
            headers=admin_headers,
        )
        assert deleted.status_code == 204

    def test_unknown_mapping_is_rejected(self, client, admin_headers, federation_setup):
        response = client.put(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/saml2",
            headers=admin_headers,
            json={"protocol": {"mapping_id": "nope"}},
        )
        assert response.status_code == 400


class TestFederatedAuth:
    """The bearer-token exchange that yields an unscoped Keystone token."""

    def test_maps_to_a_pre_existing_user(self, client, oidc_client, federation_setup):
        """The point of type: local — an account created ahead of first login."""
        user = db.create_user(name="alice@example.org", domain_id="default")
        token = _access_token(oidc_client, "alice", "alice@example.org")

        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()["token"]
        assert body["user"]["id"] == user.id
        assert body["user"]["name"] == "alice@example.org"
        assert body["methods"] == [PROTOCOL]
        assert body["user"]["OS-FEDERATION"]["identity_provider"]["id"] == IDP
        # Unscoped: no project, no catalog.
        assert "project" not in body
        assert "catalog" not in body
        assert response.headers["X-Subject-Token"]

    def test_unknown_local_user_is_rejected(self, client, oidc_client, federation_setup):
        token = _access_token(oidc_client, "mallory", "mallory@example.org")

        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_missing_bearer_token_is_rejected(self, client, federation_setup):
        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth"
        )
        assert response.status_code == 401

    def test_garbage_bearer_token_is_rejected(self, client, federation_setup):
        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": "Bearer not-a-token"},
        )
        assert response.status_code == 401

    def test_unknown_protocol_is_rejected(self, client, oidc_client, federation_setup):
        db.create_user(name="alice@example.org", domain_id="default")
        token = _access_token(oidc_client, "alice", "alice@example.org")

        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/saml2/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_disabled_provider_is_rejected(
        self, client, oidc_client, admin_headers, federation_setup
    ):
        db.create_user(name="alice@example.org", domain_id="default")
        token = _access_token(oidc_client, "alice", "alice@example.org")
        client.patch(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}",
            headers=admin_headers,
            json={"identity_provider": {"enabled": False}},
        )

        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestFederatedScoping:
    """What a federated user may scope to, and what rescoping produces."""

    @pytest.fixture
    def federated_token(self, client, oidc_client, federation_setup):
        """A user with a role on one project, authenticated federatively."""
        user = db.create_user(name="alice@example.org", domain_id="default")
        project = db.create_project(name="tenant-a", domain_id="default")
        role = db.create_role(name="member")
        db.assign_role_to_user_on_project(role.id, user.id, project.id)
        db.create_project(name="tenant-b", domain_id="default")

        token = _access_token(oidc_client, "alice", "alice@example.org")
        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.headers["X-Subject-Token"], user, project

    def test_lists_only_projects_the_user_holds_a_role_on(self, client, federated_token):
        unscoped, _user, project = federated_token

        response = client.get("/v3/OS-FEDERATION/projects", headers={"X-Auth-Token": unscoped})
        assert response.status_code == 200
        assert [p["id"] for p in response.json()["projects"]] == [project.id]

    def test_lists_domains(self, client, federated_token):
        unscoped, _user, _project = federated_token

        response = client.get("/v3/OS-FEDERATION/domains", headers={"X-Auth-Token": unscoped})
        assert [d["id"] for d in response.json()["domains"]] == ["default"]

    def test_rescoping_keeps_the_federated_identity(self, client, federated_token):
        unscoped, user, project = federated_token

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {"methods": ["token"], "token": {"id": unscoped}},
                    "scope": {"project": {"id": project.id}},
                }
            },
        )
        assert response.status_code == 200
        body = response.json()["token"]
        assert body["user"]["id"] == user.id
        assert body["project"]["id"] == project.id
        assert [role["name"] for role in body["roles"]] == ["member"]
        assert body["user"]["OS-FEDERATION"]["identity_provider"]["id"] == IDP
        assert "catalog" in body

    def test_revoking_the_role_removes_the_project(self, client, federated_token):
        unscoped, user, project = federated_token
        db._role_assignments = [
            a
            for a in db._role_assignments
            if not (a.user_id == user.id and a.project_id == project.id)
        ]

        response = client.get("/v3/OS-FEDERATION/projects", headers={"X-Auth-Token": unscoped})
        assert response.json()["projects"] == []


class TestMappedGroupsAndProjects:
    """Group and project assignment through a mapping."""

    def test_groups_grant_scopable_projects(self, client, oidc_client, admin_headers):
        db.create_user(name="bob@example.org", domain_id="default")
        group = db.create_group(name="hpc-users", domain_id="default")
        project = db.create_project(name="shared", domain_id="default")
        role = db.create_role(name="member")
        db.assign_role_to_group_on_project(role.id, group.id, project.id)

        client.put(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}",
            headers=admin_headers,
            json={"identity_provider": {"domain_id": "default"}},
        )
        client.put(
            "/v3/OS-FEDERATION/mappings/group-map",
            headers=admin_headers,
            json={
                "mapping": {
                    "rules": [
                        {
                            "local": [
                                {"user": {"name": "{0}", "type": "local"}},
                                {"groups": "{1}"},
                            ],
                            "remote": [{"type": "email"}, {"type": "groups"}],
                        }
                    ]
                }
            },
        )
        client.put(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}",
            headers=admin_headers,
            json={"protocol": {"mapping_id": "group-map"}},
        )

        token = _access_token(oidc_client, "bob", "bob@example.org", groups=["hpc-users"])
        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        unscoped = response.headers["X-Subject-Token"]

        projects = client.get(
            "/v3/OS-FEDERATION/projects", headers={"X-Auth-Token": unscoped}
        ).json()["projects"]
        assert [p["id"] for p in projects] == [project.id]

    def test_ephemeral_user_is_created(self, client, oidc_client, admin_headers):
        client.put(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}",
            headers=admin_headers,
            json={"identity_provider": {"domain_id": "default"}},
        )
        client.put(
            "/v3/OS-FEDERATION/mappings/ephemeral-map",
            headers=admin_headers,
            json={
                "mapping": {
                    "rules": [
                        {
                            "local": [{"user": {"name": "{0}", "type": "ephemeral"}}],
                            "remote": [{"type": "email"}],
                        }
                    ]
                }
            },
        )
        client.put(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}",
            headers=admin_headers,
            json={"protocol": {"mapping_id": "ephemeral-map"}},
        )

        token = _access_token(oidc_client, "carol", "carol@example.org")
        response = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert db.get_user_by_name("carol@example.org", "default") is not None


class TestServiceProviders:
    """Service provider registry."""

    def test_crud(self, client, admin_headers):
        created = client.put(
            "/v3/OS-FEDERATION/service_providers/peer",
            headers=admin_headers,
            json={
                "service_provider": {
                    "auth_url": "https://peer/v3/OS-FEDERATION/identity_providers/x/protocols/y/auth",
                    "sp_url": "https://peer/Shibboleth.sso/SAML2/ECP",
                }
            },
        )
        assert created.status_code == 201

        listed = client.get("/v3/OS-FEDERATION/service_providers", headers=admin_headers)
        assert [sp["id"] for sp in listed.json()["service_providers"]] == ["peer"]

        assert (
            client.delete(
                "/v3/OS-FEDERATION/service_providers/peer", headers=admin_headers
            ).status_code
            == 204
        )


class TestFederatedRescopePrivilege:
    """A federated token carries only the roles its user was actually granted."""

    def test_rescoping_to_an_unassigned_project_grants_nothing(
        self, client, oidc_client, federation_setup
    ):
        """The default-role convenience must not apply to a federated identity.

        For simple password setups the emulator hands a user with no assignments
        an "admin" role so the token is usable. Letting that fire on a federated
        rescope would make the token claim a role nobody granted, which is the
        opposite of what mapping a federated user onto real assignments is for.
        """
        db.create_user(name="alice@example.org", domain_id="default")
        stranger = db.create_project(name="not-hers", domain_id="default")

        token = _access_token(oidc_client, "alice", "alice@example.org")
        unscoped = client.post(
            f"/v3/OS-FEDERATION/identity_providers/{IDP}/protocols/{PROTOCOL}/auth",
            headers={"Authorization": f"Bearer {token}"},
        ).headers["X-Subject-Token"]

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {"methods": ["token"], "token": {"id": unscoped}},
                    "scope": {"project": {"id": stranger.id}},
                }
            },
        )

        assert response.json()["token"]["roles"] == []
        from emulator.core.simple_auth import validate_token_simple

        assert validate_token_simple(response.headers["X-Subject-Token"]).is_admin is False

    def test_a_password_token_keeps_the_convenience_fallback(self, client):
        """The fallback still applies where it always did, so setups keep working."""
        project = db.create_project(name="plain-tenant", domain_id="default")
        db.create_user(name="plain", domain_id="default")

        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "plain",
                                "domain": {"id": "default"},
                                "password": "pw",
                            }
                        },
                    },
                    "scope": {"project": {"id": project.id}},
                }
            },
        )
        assert [r["name"] for r in response.json()["token"]["roles"]] == ["admin"]
