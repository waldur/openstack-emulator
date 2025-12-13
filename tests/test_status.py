"""Tests for Status UI endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    db._servers.clear()
    db._volumes.clear()
    db._snapshots.clear()
    db._networks.clear()
    db._subnets.clear()
    db._ports.clear()
    db._routers.clear()
    db._floating_ips.clear()
    db._security_groups.clear()
    db._security_group_rules.clear()
    db._keypairs.clear()
    db._init_default_flavors()
    db._init_default_images()
    db._init_default_glance_images()
    db._init_default_keystone_data()
    db._init_default_volume_types()
    db._init_default_neutron_data()
    yield


@pytest.fixture
def client():
    """Create test client."""
    apps = create_all_service_apps()
    return TestClient(apps["status"])


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "status"


class TestStatusPage:
    """Test main status page."""

    def test_status_page_returns_html(self, client):
        """Test that status page returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_status_page_contains_title(self, client):
        """Test that status page contains expected title."""
        response = client.get("/")
        assert "OPENSTACK EMULATOR" in response.text

    def test_status_page_contains_services(self, client):
        """Test that status page shows service information."""
        response = client.get("/")
        assert "KEYSTONE" in response.text
        assert "NOVA" in response.text
        assert "CINDER" in response.text
        assert "GLANCE" in response.text
        assert "NEUTRON" in response.text

    def test_status_page_contains_resource_tabs(self, client):
        """Test that status page contains resource tabs."""
        response = client.get("/")
        assert "Compute" in response.text
        assert "Storage" in response.text
        assert "Network" in response.text
        assert "Identity" in response.text

    def test_status_page_shows_default_flavors(self, client):
        """Test that status page shows default flavors."""
        response = client.get("/")
        # Default flavors should be present
        assert "m1.tiny" in response.text
        assert "m1.small" in response.text

    def test_status_page_shows_default_images(self, client):
        """Test that status page shows default images."""
        response = client.get("/")
        # Default Glance images should be present
        assert "cirros" in response.text or "ubuntu" in response.text

    def test_status_page_shows_default_networks(self, client):
        """Test that status page shows default networks."""
        response = client.get("/")
        # Default networks should be present
        assert "external" in response.text or "private" in response.text


class TestApiStatus:
    """Test JSON API status endpoint."""

    def test_api_status_returns_json(self, client):
        """Test that API status endpoint returns JSON."""
        response = client.get("/api/status")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_api_status_contains_services(self, client):
        """Test that API status contains services information."""
        response = client.get("/api/status")
        data = response.json()
        assert "services" in data
        assert "keystone" in data["services"]
        assert "nova" in data["services"]
        assert "cinder" in data["services"]
        assert "glance" in data["services"]
        assert "neutron" in data["services"]

    def test_api_status_contains_resource_counts(self, client):
        """Test that API status contains resource counts."""
        response = client.get("/api/status")
        data = response.json()
        assert "resources" in data
        assert "servers" in data["resources"]
        assert "volumes" in data["resources"]
        assert "images" in data["resources"]
        assert "networks" in data["resources"]
        assert "projects" in data["resources"]
        assert "users" in data["resources"]

    def test_api_status_service_structure(self, client):
        """Test that each service has expected structure."""
        response = client.get("/api/status")
        data = response.json()
        for service_name, service_info in data["services"].items():
            assert "name" in service_info
            assert "port" in service_info
            assert "healthy" in service_info
            assert isinstance(service_info["healthy"], bool)

    def test_api_status_resource_counts_are_integers(self, client):
        """Test that resource counts are integers."""
        response = client.get("/api/status")
        data = response.json()
        for resource_name, count in data["resources"].items():
            assert isinstance(count, int)
            assert count >= 0

    def test_api_status_default_resource_counts(self, client):
        """Test that default resources are counted."""
        response = client.get("/api/status")
        data = response.json()
        # Should have default flavors
        assert data["resources"]["flavors"] >= 5
        # Should have default images
        assert data["resources"]["images"] >= 1
        # Should have default networks
        assert data["resources"]["networks"] >= 1
        # Should have admin project
        assert data["resources"]["projects"] >= 1
        # Should have admin user
        assert data["resources"]["users"] >= 1


class TestStatusWithData:
    """Test status page with created resources."""

    def test_status_shows_created_server(self, client):
        """Test that status page shows created servers."""
        # Create a server
        from emulator.core.models import Server, ServerStatus

        server = Server(
            id="test-server-id",
            name="test-server",
            tenant_id="admin",
            user_id="admin",
            flavor_id="1",
            image_id="test-image",
            status=ServerStatus.ACTIVE,
        )
        db._servers[server.id] = server

        response = client.get("/")
        assert "test-server" in response.text

    def test_status_shows_created_volume(self, client):
        """Test that status page shows created volumes."""
        from emulator.core.models import Volume, VolumeStatus

        volume = Volume(
            id="test-volume-id",
            name="test-volume",
            size=10,
            status=VolumeStatus.AVAILABLE,
            project_id="admin",
        )
        db._volumes[volume.id] = volume

        response = client.get("/")
        assert "test-volume" in response.text

    def test_api_status_counts_created_resources(self, client):
        """Test that API status counts created resources."""
        from emulator.core.models import Server, ServerStatus, Volume, VolumeStatus

        # Get initial counts
        response = client.get("/api/status")
        initial_data = response.json()
        initial_servers = initial_data["resources"]["servers"]
        initial_volumes = initial_data["resources"]["volumes"]

        # Create a server
        server = Server(
            id="test-server-id-2",
            name="test-server-2",
            tenant_id="admin",
            user_id="admin",
            flavor_id="1",
            image_id="test-image",
            status=ServerStatus.ACTIVE,
        )
        db._servers[server.id] = server

        # Create a volume
        volume = Volume(
            id="test-volume-id-2",
            name="test-volume-2",
            size=10,
            status=VolumeStatus.AVAILABLE,
            project_id="admin",
        )
        db._volumes[volume.id] = volume

        # Check counts increased
        response = client.get("/api/status")
        new_data = response.json()
        assert new_data["resources"]["servers"] == initial_servers + 1
        assert new_data["resources"]["volumes"] == initial_volumes + 1


class TestAuthentication:
    """Test authentication endpoints."""

    def test_login_success(self, client):
        """Test successful login."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["name"] == "admin"
        # Check cookie is set
        assert "auth_token" in response.cookies

    def test_login_with_project(self, client):
        """Test login with specific project."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus", "project_name": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["name"] == "admin"

    def test_login_invalid_user(self, client):
        """Test login with invalid username."""
        response = client.post(
            "/api/login",
            json={"username": "nonexistent", "password": "s4l4dus"},
        )
        assert response.status_code == 401
        assert "Invalid username" in response.json()["error"]["message"]

    def test_login_invalid_project(self, client):
        """Test login with invalid project."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus", "project_name": "nonexistent"},
        )
        assert response.status_code == 401
        assert "Project not found" in response.json()["error"]["message"]

    def test_logout(self, client):
        """Test logout."""
        # First login
        login_response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        assert login_response.status_code == 200

        # Then logout
        response = client.post("/api/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

    def test_session_authenticated(self, client):
        """Test session endpoint when authenticated."""
        # First login
        login_response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        token = login_response.cookies.get("auth_token")

        # Check session
        response = client.get("/api/session", cookies={"auth_token": token})
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["name"] == "admin"

    def test_session_unauthenticated(self, client):
        """Test session endpoint when not authenticated."""
        response = client.get("/api/session")
        assert response.status_code == 401


class TestServerManagement:
    """Test server management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_server_authenticated(self, client):
        """Test creating a server when authenticated."""
        token = self._login(client)
        response = client.post(
            "/api/servers",
            json={"name": "test-server", "flavor_id": "1"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["server"]["name"] == "test-server"
        assert data["server"]["status"] == "ACTIVE"

    def test_create_server_unauthenticated(self, client):
        """Test creating a server without authentication fails."""
        response = client.post(
            "/api/servers",
            json={"name": "test-server", "flavor_id": "1"},
        )
        assert response.status_code == 401

    def test_create_server_invalid_flavor(self, client):
        """Test creating a server with invalid flavor."""
        token = self._login(client)
        response = client.post(
            "/api/servers",
            json={"name": "test-server", "flavor_id": "invalid"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "Flavor not found" in response.json()["error"]["message"]

    def test_delete_server(self, client):
        """Test deleting a server."""
        token = self._login(client)
        # Create server first
        create_response = client.post(
            "/api/servers",
            json={"name": "test-server", "flavor_id": "1"},
            cookies={"auth_token": token},
        )
        server_id = create_response.json()["server"]["id"]

        # Delete server
        response = client.delete(f"/api/servers/{server_id}", cookies={"auth_token": token})
        assert response.status_code == 200
        assert response.json()["message"] == "Server deleted"

    def test_server_action_start_stop(self, client):
        """Test server start and stop actions."""
        token = self._login(client)
        # Create server first
        create_response = client.post(
            "/api/servers",
            json={"name": "test-server", "flavor_id": "1"},
            cookies={"auth_token": token},
        )
        server_id = create_response.json()["server"]["id"]

        # Stop server
        response = client.post(
            f"/api/servers/{server_id}/action",
            json={"action": "stop"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        assert "stop" in response.json()["message"]

        # Start server
        response = client.post(
            f"/api/servers/{server_id}/action",
            json={"action": "start"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        assert "start" in response.json()["message"]


class TestVolumeManagement:
    """Test volume management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_volume(self, client):
        """Test creating a volume."""
        token = self._login(client)
        response = client.post(
            "/api/volumes",
            json={"name": "test-volume", "size": 10},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume"]["name"] == "test-volume"
        assert data["volume"]["status"] == "available"

    def test_delete_volume(self, client):
        """Test deleting a volume."""
        token = self._login(client)
        # Create volume first
        create_response = client.post(
            "/api/volumes",
            json={"name": "test-volume", "size": 10},
            cookies={"auth_token": token},
        )
        volume_id = create_response.json()["volume"]["id"]

        # Delete volume
        response = client.delete(f"/api/volumes/{volume_id}", cookies={"auth_token": token})
        assert response.status_code == 200


class TestNetworkManagement:
    """Test network management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_network(self, client):
        """Test creating a network."""
        token = self._login(client)
        response = client.post(
            "/api/networks",
            json={"name": "test-network"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["network"]["name"] == "test-network"
        assert data["network"]["status"] == "ACTIVE"

    def test_create_external_network(self, client):
        """Test creating an external network."""
        token = self._login(client)
        response = client.post(
            "/api/networks",
            json={"name": "test-external", "external": True},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200

    def test_delete_network(self, client):
        """Test deleting a network."""
        token = self._login(client)
        # Create network first
        create_response = client.post(
            "/api/networks",
            json={"name": "test-network"},
            cookies={"auth_token": token},
        )
        network_id = create_response.json()["network"]["id"]

        # Delete network
        response = client.delete(f"/api/networks/{network_id}", cookies={"auth_token": token})
        assert response.status_code == 200

    def test_create_subnet(self, client):
        """Test creating a subnet."""
        token = self._login(client)
        # Create network first
        net_response = client.post(
            "/api/networks",
            json={"name": "test-network"},
            cookies={"auth_token": token},
        )
        network_id = net_response.json()["network"]["id"]

        # Create subnet
        response = client.post(
            "/api/subnets",
            json={"name": "test-subnet", "network_id": network_id, "cidr": "10.0.0.0/24"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subnet"]["name"] == "test-subnet"
        assert data["subnet"]["cidr"] == "10.0.0.0/24"

    def test_create_router(self, client):
        """Test creating a router."""
        token = self._login(client)
        response = client.post(
            "/api/routers",
            json={"name": "test-router"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["router"]["name"] == "test-router"
        assert data["router"]["status"] == "ACTIVE"


class TestSecurityGroupManagement:
    """Test security group management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_security_group(self, client):
        """Test creating a security group."""
        token = self._login(client)
        response = client.post(
            "/api/security_groups",
            json={"name": "test-sg", "description": "Test security group"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["security_group"]["name"] == "test-sg"

    def test_cannot_delete_default_security_group(self, client):
        """Test that default security group cannot be deleted."""
        token = self._login(client)
        # Find default security group
        default_sg = None
        for sg in db.list_security_groups():
            if sg.name == "default":
                default_sg = sg
                break

        if default_sg:
            response = client.delete(
                f"/api/security_groups/{default_sg.id}",
                cookies={"auth_token": token},
            )
            assert response.status_code == 400
            assert "default" in response.json()["error"]["message"]


class TestProjectManagement:
    """Test project management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_project(self, client):
        """Test creating a project."""
        token = self._login(client)
        response = client.post(
            "/api/projects",
            json={"name": "test-project", "description": "Test project"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["name"] == "test-project"
        assert data["project"]["enabled"] is True

    def test_create_duplicate_project(self, client):
        """Test creating a project with existing name fails."""
        token = self._login(client)
        # Create project
        client.post(
            "/api/projects",
            json={"name": "unique-project"},
            cookies={"auth_token": token},
        )
        # Try to create duplicate
        response = client.post(
            "/api/projects",
            json={"name": "unique-project"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["error"]["message"]

    def test_cannot_delete_admin_project(self, client):
        """Test that admin project cannot be deleted."""
        token = self._login(client)
        admin_project = db.get_project_by_name("admin")
        response = client.delete(
            f"/api/projects/{admin_project.id}",
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "admin" in response.json()["error"]["message"]


class TestUserManagement:
    """Test user management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_user(self, client):
        """Test creating a user."""
        token = self._login(client)
        response = client.post(
            "/api/users",
            json={"name": "testuser", "password": "testpass", "email": "test@example.com"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["name"] == "testuser"
        assert data["user"]["enabled"] is True

    def test_create_duplicate_user(self, client):
        """Test creating a user with existing name fails."""
        token = self._login(client)
        # Try to create user with existing name
        response = client.post(
            "/api/users",
            json={"name": "admin", "password": "s4l4dus"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["error"]["message"]

    def test_cannot_delete_admin_user(self, client):
        """Test that admin user cannot be deleted."""
        token = self._login(client)
        admin_user = db.get_user_by_name("admin")
        response = client.delete(
            f"/api/users/{admin_user.id}",
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "admin" in response.json()["error"]["message"]


class TestImageManagement:
    """Test image management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_image(self, client):
        """Test creating an image."""
        token = self._login(client)
        response = client.post(
            "/api/images",
            json={"name": "test-image", "disk_format": "qcow2", "container_format": "bare"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["image"]["name"] == "test-image"
        # New images start in 'queued' status until data is uploaded
        assert data["image"]["status"] == "queued"

    def test_delete_image(self, client):
        """Test deleting an image."""
        token = self._login(client)
        # Create image first
        create_response = client.post(
            "/api/images",
            json={"name": "test-image"},
            cookies={"auth_token": token},
        )
        image_id = create_response.json()["image"]["id"]

        # Delete image
        response = client.delete(f"/api/images/{image_id}", cookies={"auth_token": token})
        assert response.status_code == 200


class TestSnapshotManagement:
    """Test snapshot management endpoints."""

    def _login(self, client):
        """Helper to login and return auth token."""
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        return response.cookies.get("auth_token")

    def test_create_snapshot(self, client):
        """Test creating a snapshot."""
        token = self._login(client)
        # Create volume first
        vol_response = client.post(
            "/api/volumes",
            json={"name": "test-volume", "size": 10},
            cookies={"auth_token": token},
        )
        volume_id = vol_response.json()["volume"]["id"]

        # Create snapshot
        response = client.post(
            "/api/snapshots",
            json={"name": "test-snapshot", "volume_id": volume_id},
            cookies={"auth_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["snapshot"]["name"] == "test-snapshot"
        assert data["snapshot"]["status"] == "available"

    def test_create_snapshot_invalid_volume(self, client):
        """Test creating a snapshot with invalid volume."""
        token = self._login(client)
        response = client.post(
            "/api/snapshots",
            json={"name": "test-snapshot", "volume_id": "invalid-id"},
            cookies={"auth_token": token},
        )
        assert response.status_code == 400
        assert "Volume not found" in response.json()["error"]["message"]


class TestStatusPageAuthentication:
    """Test status page with authentication."""

    def test_status_page_shows_login_button_unauthenticated(self, client):
        """Test that status page shows login button when not authenticated."""
        response = client.get("/")
        assert "LOGIN" in response.text
        assert "READ-ONLY MODE" in response.text

    def test_status_page_shows_user_info_authenticated(self, client):
        """Test that status page shows user info when authenticated."""
        # Login first
        login_response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        token = login_response.cookies.get("auth_token")

        # Get status page
        response = client.get("/", cookies={"auth_token": token})
        assert "admin" in response.text
        assert "Logout" in response.text

    def test_status_page_shows_create_buttons_authenticated(self, client):
        """Test that status page shows create buttons when authenticated."""
        # Login first
        login_response = client.post(
            "/api/login",
            json={"username": "admin", "password": "s4l4dus"},
        )
        token = login_response.cookies.get("auth_token")

        # Get status page
        response = client.get("/", cookies={"auth_token": token})
        assert "Create Server" in response.text
        assert "Create Volume" in response.text
        assert "Create Network" in response.text
