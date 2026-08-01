"""SDK tests for OIDC-federated Keystone authentication against the emulator.

These drive the real keystoneauth ``v3oidcpassword`` / ``v3oidcaccesstoken``
plugins end to end: fetch the provider's discovery document, exchange a password
grant for an access token, present it to Keystone's OS-FEDERATION auth endpoint,
and rescope the resulting unscoped token to a project.

The scenario mirrors the reason federation matters for an agent that manages
OpenStack tenants: the agent creates the Keystone user and grants it a role
ahead of time, and the federated login has to resolve to *that* user rather than
minting a new one.
"""

import openstack
import pytest
from openstack.connection import Connection

from emulator.core.database import db

IDP = "keycloak"
PROTOCOL = "openid"
CLIENT_ID = "waldur"
CLIENT_SECRET = "secret"
EMAIL = "alice@example.org"


@pytest.fixture
def federated_setup(openstack_connection: Connection, emulator_servers):
    """Provision everything an agent would, plus the federation wiring.

    Returns the Keystone user and project the federated login should land on.
    """
    identity = openstack_connection.identity

    # What the site agent does: pre-create the account named after the user's
    # email, and grant it a role on the tenant it manages.
    user = identity.create_user(name=EMAIL, domain_id="default", email=EMAIL)
    project = identity.create_project(name="tenant-a", domain_id="default")
    role = identity.create_role(name="member")
    identity.assign_project_role_to_user(project.id, user.id, role.id)

    # What the operator does: trust the provider and map its email claim onto
    # the local account.
    db.create_identity_provider(idp_id=IDP, description="Test IdP", domain_id="default")
    db.create_federation_mapping(
        mapping_id="email-map",
        rules=[
            {
                "local": [{"user": {"name": "{0}", "type": "local"}}],
                "remote": [{"type": "email"}],
            }
        ],
    )
    db.create_federation_protocol(IDP, PROTOCOL, "email-map")

    # And the provider's own registration of the client and end user.
    db.create_oidc_client(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    db.create_oidc_user(username="alice", password="pw", email=EMAIL, name="Alice")

    return user, project


def _connect(emulator_servers, **overrides):
    """Build a connection using the v3oidcpassword plugin."""
    keystone = emulator_servers.get_url("keystone") + "/v3"
    oidc = emulator_servers.get_url("oidc")
    kwargs = {
        "auth_type": "v3oidcpassword",
        "auth_url": keystone,
        "identity_provider": IDP,
        "protocol": PROTOCOL,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "discovery_endpoint": f"{oidc}/.well-known/openid-configuration",
        "username": "alice",
        "password": "pw",
        "identity_endpoint_override": keystone,
        "region_name": "RegionOne",
    }
    kwargs.update(overrides)
    return openstack.connect(**kwargs)


class TestFederatedLogin:
    """A federated login resolves to the pre-created account."""

    def test_unscoped_login_identifies_the_existing_user(self, emulator_servers, federated_setup):
        user, _project = federated_setup

        conn = _connect(emulator_servers)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        assert auth_ref.user_id == user.id
        assert auth_ref.username == EMAIL
        assert auth_ref.project_id is None
        conn.close()

    def test_scoped_login_grants_the_assigned_role(self, emulator_servers, federated_setup):
        user, project = federated_setup

        conn = _connect(emulator_servers, project_id=project.id)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        assert auth_ref.user_id == user.id
        assert auth_ref.project_id == project.id
        assert auth_ref.role_names == ["member"]
        conn.close()

    def test_scopable_projects_are_discoverable(self, emulator_servers, federated_setup):
        _user, project = federated_setup

        conn = _connect(emulator_servers)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)
        # Addressed absolutely rather than through the catalog: an unscoped
        # token carries no catalog, which is exactly why project discovery has
        # to be possible without one.
        response = conn.session.get(
            emulator_servers.get_url("keystone") + "/v3/OS-FEDERATION/projects",
            headers={"X-Auth-Token": auth_ref.auth_token},
            authenticated=False,
        )

        assert [p["id"] for p in response.json()["projects"]] == [project.id]
        conn.close()

    def test_access_token_plugin_works_too(self, emulator_servers, federated_setup):
        """v3oidcaccesstoken skips the provider and presents a token directly."""
        user, project = federated_setup

        bootstrap = _connect(emulator_servers)
        access_token = bootstrap.session.auth._get_access_token(
            bootstrap.session,
            {
                "grant_type": "password",
                "username": "alice",
                "password": "pw",
                "scope": "openid profile",
            },
        )
        bootstrap.close()

        conn = openstack.connect(
            auth_type="v3oidcaccesstoken",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            identity_provider=IDP,
            protocol=PROTOCOL,
            access_token=access_token,
            project_id=project.id,
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
            region_name="RegionOne",
        )
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        assert auth_ref.user_id == user.id
        assert auth_ref.project_id == project.id
        conn.close()


class TestFederatedLoginFailures:
    """Cases that must not produce a usable identity."""

    def test_unknown_user_is_refused(self, emulator_servers, federated_setup):
        """A local mapping must not create an account for an unknown login."""
        db.create_oidc_user(username="mallory", password="pw", email="mallory@example.org")

        conn = _connect(emulator_servers, username="mallory")
        with pytest.raises(Exception):  # noqa: B017 - keystoneauth raises Unauthorized
            conn.session.auth.get_auth_ref(conn.session)
        conn.close()

    def test_wrong_password_is_refused(self, emulator_servers, federated_setup):
        conn = _connect(emulator_servers, password="wrong")
        with pytest.raises(Exception):  # noqa: B017
            conn.session.auth.get_auth_ref(conn.session)
        conn.close()

    def test_revoked_role_removes_access_to_the_project(self, emulator_servers, federated_setup):
        user, project = federated_setup
        db._role_assignments = [
            a
            for a in db._role_assignments
            if not (a.user_id == user.id and a.project_id == project.id)
        ]

        conn = _connect(emulator_servers)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)
        response = conn.session.get(
            emulator_servers.get_url("keystone") + "/v3/OS-FEDERATION/projects",
            headers={"X-Auth-Token": auth_ref.auth_token},
            authenticated=False,
        )

        assert response.json()["projects"] == []
        conn.close()
