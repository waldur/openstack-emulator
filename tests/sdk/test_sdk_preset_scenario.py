"""End-to-end scenario over the waldur-site-agent preset, driven by openstacksdk.

This is the scenario the emulator's federation and quota work exists to support:
an out-of-process agent provisions a tenant with per-volume-type and object
storage quotas, and a user it pre-created then signs in through an identity
provider and finds that tenant.

Everything here goes through the real SDK and the real keystoneauth OIDC plugin,
so a contract mismatch fails the test rather than passing silently.
"""

import openstack
import pytest
from openstack.connection import Connection

from emulator.core.database import db
from emulator.core.presets.loader import PresetLoader

IDP = "keycloak"
PROTOCOL = "openid"


@pytest.fixture
def preset(openstack_connection: Connection):
    """Load the shipped preset and return the managed tenant."""
    result = PresetLoader(db).load_preset_by_name("waldur-site-agent")
    assert result.success, result.errors

    managed = db.get_domain_by_name("managed")
    assert managed is not None
    project = db.get_project_by_name("demo-tenant", managed.id)
    assert project is not None
    return project


def _federated_connection(emulator_servers, username, **overrides):
    """Connect as a federated end user through the embedded provider."""
    keystone = emulator_servers.get_url("keystone") + "/v3"
    kwargs = {
        "auth_type": "v3oidcpassword",
        "auth_url": keystone,
        "identity_provider": IDP,
        "protocol": PROTOCOL,
        "client_id": "waldur",
        "client_secret": "secret",
        "discovery_endpoint": (
            emulator_servers.get_url("oidc") + "/.well-known/openid-configuration"
        ),
        "username": username,
        "password": "password",
        "identity_endpoint_override": keystone,
        "region_name": "RegionOne",
    }
    kwargs.update(overrides)
    return openstack.connect(**kwargs)


class TestAgentProvisioning:
    """What the agent does: tenant, quotas, memberships."""

    def test_tenant_is_tagged_and_in_the_managed_domain(
        self, openstack_connection: Connection, preset
    ):
        project = openstack_connection.identity.get_project(preset.id)

        assert project.name == "demo-tenant"
        assert "managed-by-agent" in project.tags

    def test_per_volume_type_quotas_can_be_pushed(self, openstack_connection: Connection, preset):
        openstack_connection.block_storage.update_quota_set(
            preset.id, gigabytes_nvme=500, volumes_nvme=20, gigabytes=2000
        )

        quota = openstack_connection.block_storage.get_quota_set(preset.id)
        assert quota["gigabytes_nvme"] == 500
        assert quota["volumes_nvme"] == 20
        assert quota["gigabytes"] == 2000

    def test_quota_for_an_unknown_volume_type_is_rejected(
        self, openstack_connection: Connection, preset
    ):
        with pytest.raises(openstack.exceptions.SDKException):
            openstack_connection.block_storage.update_quota_set(preset.id, gigabytes_nosuchtype=10)

    def test_usage_reflects_the_provisioned_volume(self, openstack_connection: Connection, preset):
        quota = openstack_connection.block_storage.get_quota_set(preset.id, usage=True)

        # The SDK flattens a usage response: limits stay on the resource and
        # in_use values are collected under `usage`.
        assert quota.usage["gigabytes"] == 20
        assert quota.usage["gigabytes_nvme"] == 20

    def test_object_storage_quota_is_readable(self, openstack_connection: Connection, preset):
        account = db.get_swift_account(f"AUTH_{preset.id}", create=False)

        assert account is not None
        assert account.sysmeta["quota-bytes"] == "10737418240"

    def test_rating_summary_covers_the_tenant(
        self, openstack_connection: Connection, emulator_servers, preset
    ):
        # Addressed absolutely: the catalog hardcodes the standard ports, which
        # the ephemeral ports these fixtures bind do not match.
        response = openstack_connection.session.get(
            emulator_servers.get_url("cloudkitty") + "/v2/summary",
            params={"groupby": "project_id"},
            authenticated=False,
            headers={"X-Auth-Token": openstack_connection.session.get_token()},
        )

        body = response.json()
        rows = [dict(zip(body["columns"], row)) for row in body["results"]]
        by_project = {row["project_id"]: row for row in rows}
        assert preset.id in by_project
        # One instance and a 20 GB volume.
        assert by_project[preset.id]["qty"] == pytest.approx(21.0)


class TestFederatedAccess:
    """What the end user does: sign in and find the tenant."""

    def test_pre_created_account_is_reused(self, emulator_servers, preset):
        expected = db.get_user_by_name("alice@example.org", preset.domain_id)
        assert expected is not None

        conn = _federated_connection(emulator_servers, "alice")
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        assert auth_ref.user_id == expected.id
        conn.close()

    def test_direct_role_grants_the_tenant(self, emulator_servers, preset):
        conn = _federated_connection(emulator_servers, "alice", project_id=preset.id)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        assert auth_ref.project_id == preset.id
        assert auth_ref.role_names == ["member"]
        conn.close()

    def test_group_membership_also_grants_the_tenant(self, emulator_servers, preset):
        """bob reaches demo-tenant only through the hpc-users group."""
        conn = _federated_connection(emulator_servers, "bob")
        auth_ref = conn.session.auth.get_auth_ref(conn.session)
        response = conn.session.get(
            emulator_servers.get_url("keystone") + "/v3/OS-FEDERATION/projects",
            headers={"X-Auth-Token": auth_ref.auth_token},
            authenticated=False,
        )

        assert preset.id in [p["id"] for p in response.json()["projects"]]
        conn.close()

    def test_user_without_a_local_account_is_refused(self, emulator_servers, preset):
        conn = _federated_connection(emulator_servers, "mallory")

        with pytest.raises(Exception):  # noqa: B017 - keystoneauth raises Unauthorized
            conn.session.auth.get_auth_ref(conn.session)
        conn.close()

    def test_scoped_session_can_use_the_catalog(self, emulator_servers, preset):
        """A rescoped federated token is a working session, not just an identity."""
        conn = _federated_connection(emulator_servers, "alice", project_id=preset.id)
        auth_ref = conn.session.auth.get_auth_ref(conn.session)

        catalog_types = {entry["type"] for entry in auth_ref.service_catalog.catalog}
        assert {"compute", "volumev3", "object-store", "rating"} <= catalog_types
        conn.close()
