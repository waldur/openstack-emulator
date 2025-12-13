"""Tests for Nova Compute API endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


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
    token = db.create_token(
        user_name="admin",
        project_name="admin", 
        domain_id="default"
    )
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


class TestAuthEndpoints:
    """Test authentication endpoints."""

    def test_create_token(self, client):
        """Test token creation."""
        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "admin",
                                "domain": {"name": "Default"},
                                "password": "secret",
                            }
                        },
                    }
                }
            },
        )
        assert response.status_code == 200
        assert "X-Subject-Token" in response.headers
        data = response.json()
        assert "token" in data
        assert "catalog" in data["token"]

    def test_validate_token(self, client, auth_token):
        """Test token validation."""
        response = client.get(
            "/v3/auth/tokens",
            headers={
                "X-Auth-Token": auth_token,
                "X-Subject-Token": auth_token,
            },
        )
        assert response.status_code == 200

    def test_revoke_token(self, client, auth_token):
        """Test token revocation."""
        response = client.delete(
            "/v3/auth/tokens",
            headers={
                "X-Auth-Token": auth_token,
                "X-Subject-Token": auth_token,
            },
        )
        assert response.status_code == 204


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

    def test_emulator_status(self, client):
        """Test emulator status endpoint."""
        response = client.get("/emulator/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "statistics" in data

    def test_emulator_reset(self, client, auth_token):
        """Test emulator reset endpoint."""
        # Create some data
        images_response = client.get(
            "/v2.1/images",
            headers={"X-Auth-Token": auth_token},
        )
        image_id = images_response.json()["images"][0]["id"]

        client.post(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
            json={
                "server": {
                    "name": "test",
                    "flavorRef": "1",
                    "imageRef": image_id,
                }
            },
        )

        # Reset
        response = client.post("/emulator/reset")
        assert response.status_code == 200

        # Verify servers are cleared (need new token after reset)
        new_token_response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {"user": {"name": "admin"}},
                    }
                }
            },
        )
        new_token = new_token_response.headers["X-Subject-Token"]

        servers_response = client.get(
            "/v2.1/servers",
            headers={"X-Auth-Token": new_token},
        )
        assert servers_response.json()["servers"] == []
