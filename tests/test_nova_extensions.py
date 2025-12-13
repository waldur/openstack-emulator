"""Test Nova extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

# Create Nova app for testing
service_apps = create_all_service_apps()
nova_app = service_apps["nova"]
client = TestClient(nova_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._servers.clear()
    db._tokens.clear()
    db._keypairs.clear()
    db._server_volume_attachments.clear()
    db._server_network_interfaces.clear()
    db._server_consoles.clear()
    db._server_tags.clear()
    db._init_default_flavors()
    db._init_default_images()
    db._init_nova_extensions()
    db.reset_keystone()
    yield


@pytest.fixture
def auth_token():
    """Get a valid auth token for testing."""
    # Use the keystone app to get a proper token
    keystone_app = create_all_service_apps()["keystone"]
    keystone_client = TestClient(keystone_app)

    response = keystone_client.post(
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
                "scope": {"project": {"name": "admin", "domain": {"id": "default"}}},
            }
        },
    )
    return response.headers["X-Subject-Token"]


@pytest.fixture
def test_server(auth_token):
    """Create a test server."""
    response = client.post(
        "/v2.1/servers",
        json={
            "server": {
                "name": "test-server",
                "flavorRef": "1",
                "imageRef": None,
            }
        },
        headers={"X-Auth-Token": auth_token},
    )
    assert response.status_code == 202
    return response.json()["server"]["id"]


class TestNovaExtensions:
    """Test Nova extensions endpoints."""

    def test_list_extensions(self, auth_token):
        """Test listing Nova extensions."""
        response = client.get("/v2.1/extensions", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "extensions" in data
        assert len(data["extensions"]) > 0

        # Check for specific extensions
        extension_aliases = [ext["alias"] for ext in data["extensions"]]
        assert "os-volume_attachments" in extension_aliases
        assert "os-interface" in extension_aliases
        assert "os-consoles" in extension_aliases
        assert "os-server-tags" in extension_aliases

    def test_get_extension(self, auth_token):
        """Test getting a specific extension."""
        response = client.get(
            "/v2.1/extensions/os-volume_attachments", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "extension" in data
        assert data["extension"]["alias"] == "os-volume_attachments"
        assert data["extension"]["name"] == "VolumeAttachments"

    def test_get_extension_not_found(self, auth_token):
        """Test getting a non-existent extension."""
        response = client.get("/v2.1/extensions/nonexistent", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 404


class TestServerVolumeAttachments:
    """Test server volume attachment endpoints."""

    def test_list_volume_attachments_empty(self, auth_token, test_server):
        """Test listing volume attachments for a server with none attached."""
        response = client.get(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "volumeAttachments" in data
        assert data["volumeAttachments"] == []

    def test_attach_volume_to_server(self, auth_token, test_server):
        """Test attaching a volume to a server."""
        # First create a volume using Cinder API
        cinder_app = create_all_service_apps()["cinder"]
        cinder_client = TestClient(cinder_app)

        volume_response = cinder_client.post(
            "/v3/admin/volumes",  # Use admin project since our token is for admin
            json={
                "volume": {
                    "name": "test-volume",
                    "size": 1,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert volume_response.status_code == 202
        volume_id = volume_response.json()["volume"]["id"]

        # Now attach it to the server
        response = client.post(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            json={
                "volumeAttachment": {
                    "volumeId": volume_id,
                    "device": "/dev/vdb",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "volumeAttachment" in data
        assert data["volumeAttachment"]["volumeId"] == volume_id
        assert data["volumeAttachment"]["serverId"] == test_server
        assert data["volumeAttachment"]["device"] == "/dev/vdb"

    def test_list_volume_attachments_after_attach(self, auth_token, test_server):
        """Test listing volume attachments after attaching a volume."""
        # Create and attach a volume using Cinder API
        cinder_app = create_all_service_apps()["cinder"]
        cinder_client = TestClient(cinder_app)

        volume_response = cinder_client.post(
            "/v3/admin/volumes",
            json={"volume": {"name": "test-volume", "size": 1}},
            headers={"X-Auth-Token": auth_token},
        )
        volume_id = volume_response.json()["volume"]["id"]

        client.post(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            json={"volumeAttachment": {"volumeId": volume_id}},
            headers={"X-Auth-Token": auth_token},
        )

        # List attachments
        response = client.get(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["volumeAttachments"]) == 1
        assert data["volumeAttachments"][0]["volumeId"] == volume_id


class TestServerNetworkInterfaces:
    """Test server network interface endpoints."""

    def test_list_interfaces_empty(self, auth_token, test_server):
        """Test listing interfaces for a server with none attached."""
        response = client.get(
            f"/v2.1/servers/{test_server}/os-interface",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "interfaceAttachments" in data
        assert data["interfaceAttachments"] == []

    def test_attach_interface_to_server(self, auth_token, test_server):
        """Test attaching a network interface to a server."""
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={
                "interfaceAttachment": {
                    "net_id": "test-network-id",
                    "fixed_ip": "192.168.1.100",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "interfaceAttachment" in data
        assert data["interfaceAttachment"]["net_id"] == "test-network-id"
        assert "port_id" in data["interfaceAttachment"]
        assert "mac_addr" in data["interfaceAttachment"]


class TestServerDiagnostics:
    """Test server diagnostics endpoint."""

    def test_get_server_diagnostics(self, auth_token, test_server):
        """Test getting server diagnostics."""
        response = client.get(
            f"/v2.1/servers/{test_server}/diagnostics",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "state" in data
        assert "driver" in data
        assert "hypervisor" in data
        assert "uptime" in data
        assert "num_cpus" in data
        assert "memory" in data


class TestServerConsoles:
    """Test server console endpoints."""

    def test_list_consoles_empty(self, auth_token, test_server):
        """Test listing consoles for a server with none created."""
        response = client.get(
            f"/v2.1/servers/{test_server}/consoles",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "consoles" in data
        assert data["consoles"] == []

    def test_create_console(self, auth_token, test_server):
        """Test creating a console for a server."""
        response = client.post(
            f"/v2.1/servers/{test_server}/consoles",
            json={"console": {"type": "novnc"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "console" in data
        assert data["console"]["console_type"] == "novnc"
        assert "id" in data["console"]

    def test_create_remote_console(self, auth_token, test_server):
        """Test creating a remote console for a server."""
        response = client.post(
            f"/v2.1/servers/{test_server}/remote-consoles",
            json={
                "remote_console": {
                    "type": "novnc",
                    "protocol": "vnc",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "remote_console" in data
        assert data["remote_console"]["type"] == "novnc"
        assert data["remote_console"]["protocol"] == "vnc"
        assert "url" in data["remote_console"]


class TestServerTags:
    """Test server tags endpoints."""

    def test_list_tags_empty(self, auth_token, test_server):
        """Test listing tags for a server with none set."""
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "tags" in data
        assert data["tags"] == []

    def test_add_server_tag(self, auth_token, test_server):
        """Test adding a tag to a server."""
        response = client.put(
            f"/v2.1/servers/{test_server}/tags/production",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        # Verify tag was added
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert "production" in response.json()["tags"]

    def test_replace_server_tags(self, auth_token, test_server):
        """Test replacing all tags on a server."""
        response = client.put(
            f"/v2.1/servers/{test_server}/tags",
            json={"tags": ["web", "production", "database"]},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert set(data["tags"]) == {"web", "production", "database"}

    def test_check_server_tag(self, auth_token, test_server):
        """Test checking if a server has a specific tag."""
        # Add a tag first
        client.put(
            f"/v2.1/servers/{test_server}/tags/test",
            headers={"X-Auth-Token": auth_token},
        )

        # Check tag exists
        response = client.get(
            f"/v2.1/servers/{test_server}/tags/test",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Check non-existent tag
        response = client.get(
            f"/v2.1/servers/{test_server}/tags/nonexistent",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_remove_server_tag(self, auth_token, test_server):
        """Test removing a tag from a server."""
        # Add a tag first
        client.put(
            f"/v2.1/servers/{test_server}/tags/temp",
            headers={"X-Auth-Token": auth_token},
        )

        # Remove the tag
        response = client.delete(
            f"/v2.1/servers/{test_server}/tags/temp",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify tag was removed
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert "temp" not in response.json()["tags"]

    def test_clear_server_tags(self, auth_token, test_server):
        """Test clearing all tags from a server."""
        # Add some tags first
        client.put(
            f"/v2.1/servers/{test_server}/tags",
            json={"tags": ["tag1", "tag2", "tag3"]},
            headers={"X-Auth-Token": auth_token},
        )

        # Clear all tags
        response = client.delete(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify tags are cleared
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["tags"] == []


class TestTenantIsolation:
    """Test tenant isolation for new endpoints."""

    def test_volume_attachment_tenant_isolation(self, auth_token):
        """Test that users cannot attach volumes to other tenants' servers."""
        # Create server and volume in different projects
        server_response = client.post(
            "/v2.1/servers",
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": None,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        server_id = server_response.json()["server"]["id"]

        # Create a different project and get token
        keystone_app = create_all_service_apps()["keystone"]
        keystone_client = TestClient(keystone_app)

        # Create a new project for isolation testing
        _project_response = keystone_client.post(
            "/v3/projects",
            json={
                "project": {
                    "name": "other-project",
                    "domain_id": "default",
                    "description": "Test project for isolation",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )

        # Get token scoped to the other project
        other_token_response = keystone_client.post(
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
                    "scope": {"project": {"name": "other-project", "domain": {"id": "default"}}},
                }
            },
        )
        other_token = other_token_response.headers["X-Subject-Token"]

        # Try to access volume attachments with wrong token
        response = client.get(
            f"/v2.1/servers/{server_id}/os-volume_attachments",
            headers={"X-Auth-Token": other_token},
        )
        assert response.status_code == 404  # Server not found due to tenant isolation

    def test_interface_attachment_tenant_isolation(self, auth_token):
        """Test that users cannot manage interfaces on other tenants' servers."""
        # Create server
        server_response = client.post(
            "/v2.1/servers",
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": None,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        server_id = server_response.json()["server"]["id"]

        # Create a different project and get token
        keystone_app = create_all_service_apps()["keystone"]
        keystone_client = TestClient(keystone_app)

        # Create a new project for isolation testing
        _project_response = keystone_client.post(
            "/v3/projects",
            json={
                "project": {
                    "name": "interface-test-project",
                    "domain_id": "default",
                    "description": "Test project for interface isolation",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )

        # Get token scoped to the other project
        other_token_response = keystone_client.post(
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
                    "scope": {
                        "project": {"name": "interface-test-project", "domain": {"id": "default"}}
                    },
                }
            },
        )
        other_token = other_token_response.headers["X-Subject-Token"]

        # Try to access interfaces with wrong token
        response = client.get(
            f"/v2.1/servers/{server_id}/os-interface",
            headers={"X-Auth-Token": other_token},
        )
        assert response.status_code == 404  # Server not found due to tenant isolation
