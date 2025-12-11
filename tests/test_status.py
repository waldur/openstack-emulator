"""Tests for Status UI endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.app_status import app
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
    return TestClient(app)


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
        assert "OpenStack Emulator Status" in response.text

    def test_status_page_contains_services(self, client):
        """Test that status page shows service information."""
        response = client.get("/")
        assert "Keystone" in response.text
        assert "Nova" in response.text
        assert "Cinder" in response.text
        assert "Glance" in response.text
        assert "Neutron" in response.text

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
