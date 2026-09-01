"""Tests for Nova Compute API endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import grant_scope


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    db._servers.clear()
    db._tokens.clear()
    db._keypairs.clear()
    db._init_default_flavors()
    db._init_default_images()
    db.reset_keystone()
    yield


@pytest.fixture
def client():
    """Create test client."""
    apps = create_all_service_apps()
    return TestClient(apps["nova"])


@pytest.fixture
def auth_token(client):
    """Get an authentication token by creating it directly in the database."""
    # Create token directly in database for simplified testing
    token = db.create_token(user_name="admin", project_name="admin", domain_id="default")
    return token.id


class TestVersionEndpoints:
    """Test version discovery endpoints."""

    def test_list_compute_versions(self, client):
        """Test listing compute API versions."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) >= 1

    def test_get_v21_version(self, client):
        """Test getting v2.1 version details."""
        response = client.get("/v2.1/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"]["id"] == "v2.1"
        assert data["version"]["status"] == "CURRENT"


class TestFlavorEndpoints:
    """Test flavor endpoints."""

    def test_list_flavors(self, client, auth_token):
        """Test listing flavors."""
        response = client.get(
            "/v2.1/flavors",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "flavors" in data
        assert len(data["flavors"]) >= 5  # Default flavors

    def test_list_flavors_detail(self, client, auth_token):
        """Test listing flavors with details."""
        response = client.get(
            "/v2.1/flavors/detail",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "flavors" in data
        assert "vcpus" in data["flavors"][0]
        assert "ram" in data["flavors"][0]

    def test_get_flavor(self, client, auth_token):
        """Test getting a single flavor."""
        response = client.get(
            "/v2.1/flavors/1",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flavor"]["name"] == "m1.tiny"

    def test_create_flavor(self, client, auth_token):
        """Test creating a flavor."""
        response = client.post(
            "/v2.1/flavors",
            headers={"X-Auth-Token": auth_token},
            json={
                "flavor": {
                    "name": "test.flavor",
                    "vcpus": 2,
                    "ram": 1024,
                    "disk": 20,
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flavor"]["name"] == "test.flavor"

    def test_delete_flavor(self, client, auth_token):
        """Test deleting a flavor."""
        # Create a flavor first
        create_response = client.post(
            "/v2.1/flavors",
            headers={"X-Auth-Token": auth_token},
            json={
                "flavor": {
                    "name": "to-delete",
                    "vcpus": 1,
                    "ram": 512,
                    "disk": 10,
                    "id": "to-delete",
                }
            },
        )
        assert create_response.status_code == 200

        # Delete it
        response = client.delete(
            "/v2.1/flavors/to-delete",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202


class TestImageEndpoints:
    """Test image endpoints."""

    def test_list_images(self, client, auth_token):
        """Test listing images."""
        response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        assert len(data["images"]) >= 3  # Default images

    def test_list_images_detail(self, client, auth_token):
        """Test listing images with details."""
        response = client.get(
            "/v2.1/images/detail",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        assert "status" in data["images"][0]


class TestServerEndpoints:
    """Test server endpoints."""

    def test_list_servers_empty(self, client, auth_token):
        """Test listing servers when empty."""
        response = client.get(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["servers"] == []

    def test_create_server(self, client, auth_token):
        """Test creating a server."""
        # Get an image ID
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["server"]["name"] == "test-server"
        assert "adminPass" in data["server"]

    def test_create_server_with_config_drive_true(self, client, auth_token):
        """config_drive=true must round-trip as "True" on the server detail."""
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        create_response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "cd-true",
                    "flavorRef": "1",
                    "imageRef": image_id,
                    "config_drive": True,
                }
            },
        )
        assert create_response.status_code == 202
        server_id = create_response.json()["server"]["id"]

        get_response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.status_code == 200
        assert get_response.json()["server"]["config_drive"] == "True"

    def test_create_server_with_config_drive_false(self, client, auth_token):
        """config_drive=false (or omitted) must round-trip as "" per Nova spec."""
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        create_response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "cd-false",
                    "flavorRef": "1",
                    "imageRef": image_id,
                    "config_drive": False,
                }
            },
        )
        assert create_response.status_code == 202
        server_id = create_response.json()["server"]["id"]

        get_response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.status_code == 200
        assert get_response.json()["server"]["config_drive"] == ""

    def test_create_server_without_config_drive_defaults_to_empty(self, client, auth_token):
        """When config_drive is not sent at all, the response field is the empty string."""
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        create_response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "cd-omitted",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )
        assert create_response.status_code == 202
        server_id = create_response.json()["server"]["id"]

        get_response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.status_code == 200
        assert get_response.json()["server"]["config_drive"] == ""

    def test_get_server(self, client, auth_token):
        """Test getting a server."""
        # Create a server first
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        create_response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )
        server_id = create_response.json()["server"]["id"]

        # Get the server
        response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["server"]["status"] == "ACTIVE"

    def test_delete_server(self, client, auth_token):
        """Test deleting a server."""
        # Create a server first
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        create_response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "to-delete",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )
        server_id = create_response.json()["server"]["id"]

        # Delete the server
        response = client.delete(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestServerMetadata:
    """Server metadata sub-resource.

    Nova splits the two writes that clients rely on: POST merges into what the
    server already carries, PUT replaces it wholesale, and a key goes away only
    through a DELETE of that key.
    """

    @pytest.fixture
    def server_id(self, client, auth_token):
        images_response = client.get("/v2.1/images", headers={"X-Auth-Token": auth_token})
        image_id = images_response.json()["images"][0]["id"]
        response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "meta-server",
                    "flavorRef": "1",
                    "imageRef": image_id,
                    "metadata": {"env": "staging", "owner": "team-a"},
                }
            },
        )
        assert response.status_code == 202
        return response.json()["server"]["id"]

    def test_metadata_given_at_boot_is_readable(self, client, auth_token, server_id):
        response = client.get(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["metadata"] == {"env": "staging", "owner": "team-a"}

    def test_metadata_is_on_the_server_detail(self, client, auth_token, server_id):
        response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.json()["server"]["metadata"] == {"env": "staging", "owner": "team-a"}

    def test_post_merges_and_keeps_untouched_keys(self, client, auth_token, server_id):
        response = client.post(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"env": "prod", "role": "db"}},
        )
        assert response.status_code == 200
        assert response.json()["metadata"] == {
            "env": "prod",
            "owner": "team-a",
            "role": "db",
        }

    def test_put_replaces_wholesale(self, client, auth_token, server_id):
        response = client.put(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"env": "prod"}},
        )
        assert response.status_code == 200
        assert response.json()["metadata"] == {"env": "prod"}

    def test_delete_removes_one_key(self, client, auth_token, server_id):
        response = client.delete(
            f"/v2.1/servers/{server_id}/metadata/owner",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        remaining = client.get(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
        )
        assert remaining.json()["metadata"] == {"env": "staging"}

    def test_delete_of_an_absent_key_is_404(self, client, auth_token, server_id):
        response = client.delete(
            f"/v2.1/servers/{server_id}/metadata/nope",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_get_single_item(self, client, auth_token, server_id):
        response = client.get(
            f"/v2.1/servers/{server_id}/metadata/env",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json() == {"meta": {"env": "staging"}}

    def test_put_single_item(self, client, auth_token, server_id):
        response = client.put(
            f"/v2.1/servers/{server_id}/metadata/env",
            headers={"X-Auth-Token": auth_token},
            json={"meta": {"env": "prod"}},
        )
        assert response.status_code == 200
        assert response.json() == {"meta": {"env": "prod"}}

    def test_put_single_item_rejects_key_mismatch(self, client, auth_token, server_id):
        response = client.put(
            f"/v2.1/servers/{server_id}/metadata/env",
            headers={"X-Auth-Token": auth_token},
            json={"meta": {"role": "db"}},
        )
        assert response.status_code == 400

    def test_non_string_value_is_rejected(self, client, auth_token, server_id):
        response = client.post(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"port": 8080}},
        )
        assert response.status_code == 400

    def test_oversized_value_is_rejected(self, client, auth_token, server_id):
        response = client.post(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"note": "v" * 256}},
        )
        assert response.status_code == 400

    def test_merge_over_the_quota_is_refused(self, client, auth_token, server_id):
        # The quota is checked against the result of the merge, so a small body
        # can still be refused. This is why a client that replaces metadata has
        # to delete the keys it drops before pushing the new ones.
        quota = db.get_nova_quota(db.get_project_by_name("admin", "default").id)
        quota.metadata_items = 3

        response = client.post(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"a": "1", "b": "2"}},
        )
        assert response.status_code == 403
        assert "metadata_items" in response.json()["error"]["message"]

    def test_replacing_within_the_quota_is_allowed(self, client, auth_token, server_id):
        quota = db.get_nova_quota(db.get_project_by_name("admin", "default").id)
        quota.metadata_items = 2

        response = client.put(
            f"/v2.1/servers/{server_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"env": "prod", "role": "db"}},
        )
        assert response.status_code == 200

    def test_boot_over_the_quota_is_refused(self, client, auth_token):
        quota = db.get_nova_quota(db.get_project_by_name("admin", "default").id)
        quota.metadata_items = 1
        images_response = client.get("/v2.1/images", headers={"X-Auth-Token": auth_token})
        image_id = images_response.json()["images"][0]["id"]

        response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "too-much-meta",
                    "flavorRef": "1",
                    "imageRef": image_id,
                    "metadata": {"a": "1", "b": "2"},
                }
            },
        )
        assert response.status_code == 403


class TestServerActions:
    """Test server action endpoints."""

    @pytest.fixture
    def server_id(self, client, auth_token):
        """Create a server for testing actions."""
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "action-test",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )
        return response.json()["server"]["id"]

    def test_stop_server(self, client, auth_token, server_id):
        """Test stopping a server."""
        response = client.post(
            f"/v2.1/servers/{server_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"os-stop": None},
        )
        assert response.status_code == 202

        # Verify server is stopped
        get_response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.json()["server"]["status"] == "SHUTOFF"

    def test_start_server(self, client, auth_token, server_id):
        """Test starting a stopped server."""
        # First stop it
        client.post(
            f"/v2.1/servers/{server_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"os-stop": None},
        )

        # Then start it
        response = client.post(
            f"/v2.1/servers/{server_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"os-start": None},
        )
        assert response.status_code == 202

        # Verify server is active
        get_response = client.get(
            f"/v2.1/servers/{server_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.json()["server"]["status"] == "ACTIVE"

    def test_reboot_server(self, client, auth_token, server_id):
        """Test rebooting a server."""
        response = client.post(
            f"/v2.1/servers/{server_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"reboot": {"type": "SOFT"}},
        )
        assert response.status_code == 202


class TestKeypairEndpoints:
    """Test keypair endpoints."""

    def test_list_keypairs_empty(self, client, auth_token):
        """Test listing keypairs when empty."""
        response = client.get(
            "/v2.1/os-keypairs",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["keypairs"] == []

    def test_create_keypair(self, client, auth_token):
        """Test creating a keypair."""
        response = client.post(
            "/v2.1/os-keypairs",
            headers={"X-Auth-Token": auth_token},
            json={"keypair": {"name": "test-key"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["keypair"]["name"] == "test-key"
        assert "private_key" in data["keypair"]  # Generated key

    def test_create_keypair_with_public_key(self, client, auth_token):
        """Test creating a keypair with existing public key."""
        response = client.post(
            "/v2.1/os-keypairs",
            headers={"X-Auth-Token": auth_token},
            json={
                "keypair": {
                    "name": "imported-key",
                    "public_key": "ssh-rsa AAAAB... user@example.com",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["keypair"]["name"] == "imported-key"

    def test_delete_keypair(self, client, auth_token):
        """Test deleting a keypair."""
        # Create first
        client.post(
            "/v2.1/os-keypairs",
            headers={"X-Auth-Token": auth_token},
            json={"keypair": {"name": "to-delete"}},
        )

        # Delete
        response = client.delete(
            "/v2.1/os-keypairs/to-delete",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202


class TestLimitsEndpoint:
    """Test limits endpoint."""

    def test_get_limits(self, client, auth_token):
        """Test getting compute limits."""
        response = client.get(
            "/v2.1/limits",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "limits" in data
        assert "absolute" in data["limits"]
        assert "maxTotalInstances" in data["limits"]["absolute"]


class TestEmulatorEndpoints:
    """Test emulator-specific endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestServerSecurityGroups:
    """Test GET /v2.1/servers/{id}/os-security-groups.

    This endpoint shipped without any test and later produced a run of
    unexplained 404s in production, which turned out to be indistinguishable in
    the logs from a route that does not exist.
    """

    @staticmethod
    def _create_server(client, token, name="sg-server"):
        image_id = client.get("/v2.1/images", headers={"X-Auth-Token": token}).json()["images"][0][
            "id"
        ]
        response = client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": token},
            json={"server": {"name": name, "flavorRef": "1", "imageRef": image_id}},
        )
        assert response.status_code == 202
        return response.json()["server"]["id"]

    def test_admin_token_lists_groups(self, client, auth_token):
        server_id = self._create_server(client, auth_token)

        response = client.get(
            f"/v2.1/servers/{server_id}/os-security-groups",
            headers={"X-Auth-Token": auth_token},
        )

        assert response.status_code == 200
        groups = response.json()["security_groups"]
        assert [g["name"] for g in groups] == ["default"]
        # This endpoint renames the rules key; the Neutron spelling must be gone.
        assert "rules" in groups[0]
        assert "security_group_rules" not in groups[0]

    def test_owning_tenant_lists_groups(self, client):
        project = grant_scope(project_name="tenant-a", user_name="alice")
        token = db.create_token(user_name="alice", project_name="tenant-a", domain_id="default").id
        assert db.get_project(project.id) is not None
        server_id = self._create_server(client, token)

        response = client.get(
            f"/v2.1/servers/{server_id}/os-security-groups",
            headers={"X-Auth-Token": token},
        )

        assert response.status_code == 200
        assert response.json()["security_groups"][0]["tenant_id"] == project.id

    def test_foreign_tenant_gets_404(self, client, auth_token):
        """Tenant isolation, matching Nova: another project's server is invisible."""
        server_id = self._create_server(client, auth_token, name="owned-by-admin")
        grant_scope(project_name="tenant-b", user_name="bob")
        other = db.create_token(user_name="bob", project_name="tenant-b", domain_id="default").id

        response = client.get(
            f"/v2.1/servers/{server_id}/os-security-groups",
            headers={"X-Auth-Token": other},
        )

        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Server not found"

    def test_unknown_server_gets_404(self, client, auth_token):
        response = client.get(
            "/v2.1/servers/does-not-exist/os-security-groups",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_requires_a_token(self, client):
        response = client.get("/v2.1/servers/whatever/os-security-groups")
        assert response.status_code == 401


class TestErrorFormat:
    """Every 4xx must use the OpenStack error envelope."""

    def test_unmatched_route_uses_openstack_error_body(self, client, auth_token):
        """Starlette's router raises its own HTTPException for a missing route.

        Handling only fastapi.HTTPException let these return {"detail": ...},
        so a 404 body differed depending on why it was a 404.
        """
        response = client.get(
            "/v2.1/servers/some-id/os-security_groups",
            headers={"X-Auth-Token": auth_token},
        )

        assert response.status_code == 404
        assert response.json() == {"error": {"message": "Not Found", "code": 404}}
