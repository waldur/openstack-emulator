"""Test Octavia extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

# Create Octavia app for testing
service_apps = create_all_service_apps()
octavia_app = service_apps["octavia"]
client = TestClient(octavia_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._load_balancers.clear()
    db._listeners.clear()
    db._pools.clear()
    db._pool_members.clear()
    db._health_monitors.clear()
    db._l7policies.clear()
    db._l7rules.clear()
    db._octavia_quotas.clear()
    db._tokens.clear()
    db._init_octavia_extensions()
    db.reset_keystone()
    yield


@pytest.fixture
def auth_token():
    """Get a valid auth token for testing."""
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


class TestOctaviaQuotas:
    """Test Octavia quota endpoints."""

    def test_get_quota_default(self, auth_token):
        """Test getting default quota for a project."""
        response = client.get(
            "/v2.0/lbaas/quotas/test-project", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "quota" in data
        assert data["quota"]["loadbalancer"] == 10  # Default value
        assert data["quota"]["listener"] == -1  # Unlimited
        assert data["quota"]["pool"] == 10

    def test_get_quota_detail(self, auth_token):
        """Test getting detailed quota with usage."""
        response = client.get(
            "/v2.0/lbaas/quotas/test-project/detail", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "quota" in data
        assert "loadbalancer" in data["quota"]
        assert "limit" in data["quota"]["loadbalancer"]
        assert "used" in data["quota"]["loadbalancer"]
        assert data["quota"]["loadbalancer"]["used"] == 0  # No LBs created yet

    def test_update_quota(self, auth_token):
        """Test updating project quota."""
        response = client.put(
            "/v2.0/lbaas/quotas/test-project",
            json={
                "quota": {
                    "loadbalancer": 5,
                    "pool": 20,
                    "member": 100,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["quota"]["loadbalancer"] == 5
        assert data["quota"]["pool"] == 20
        assert data["quota"]["member"] == 100

    def test_reset_quota(self, auth_token):
        """Test resetting quota to defaults."""
        # Update quota first
        client.put(
            "/v2.0/lbaas/quotas/test-project",
            json={"quota": {"loadbalancer": 5}},
            headers={"X-Auth-Token": auth_token},
        )

        # Reset quota
        response = client.delete(
            "/v2.0/lbaas/quotas/test-project",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify it's back to defaults
        get_response = client.get(
            "/v2.0/lbaas/quotas/test-project",
            headers={"X-Auth-Token": auth_token},
        )
        assert get_response.json()["quota"]["loadbalancer"] == 10  # Back to default


class TestOctaviaProviders:
    """Test Octavia provider endpoints."""

    def test_list_providers(self, auth_token):
        """Test listing load balancer providers."""
        response = client.get("/v2.0/lbaas/providers", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) > 0

        # Check for expected providers
        provider_names = [provider["name"] for provider in data["providers"]]
        assert "amphora" in provider_names
        assert "ovn" in provider_names

    def test_get_provider(self, auth_token):
        """Test getting a specific provider."""
        response = client.get("/v2.0/lbaas/providers/amphora", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "provider" in data
        assert data["provider"]["name"] == "amphora"
        assert "description" in data["provider"]

    def test_get_provider_not_found(self, auth_token):
        """Test getting a non-existent provider."""
        response = client.get(
            "/v2.0/lbaas/providers/nonexistent", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 404


class TestOctaviaFlavors:
    """Test Octavia flavor endpoints."""

    def test_list_flavors(self, auth_token):
        """Test listing load balancer flavors."""
        response = client.get("/v2.0/lbaas/flavors", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "flavors" in data
        assert len(data["flavors"]) > 0

        # Check for expected flavors
        flavor_names = [flavor["name"] for flavor in data["flavors"]]
        assert "default" in flavor_names
        assert "ha" in flavor_names

    def test_get_flavor(self, auth_token):
        """Test getting a specific flavor."""
        # Get flavors first to get an ID
        list_response = client.get("/v2.0/lbaas/flavors", headers={"X-Auth-Token": auth_token})
        flavors = list_response.json()["flavors"]
        flavor_id = flavors[0]["id"]

        response = client.get(
            f"/v2.0/lbaas/flavors/{flavor_id}", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "flavor" in data
        assert data["flavor"]["id"] == flavor_id

    def test_list_flavor_profiles(self, auth_token):
        """Test listing flavor profiles."""
        response = client.get("/v2.0/lbaas/flavorprofiles", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "flavorprofiles" in data
        assert len(data["flavorprofiles"]) > 0

        # Check for expected profiles
        profile_names = [profile["name"] for profile in data["flavorprofiles"]]
        assert "default-amphora-profile" in profile_names
        assert "ha-amphora-profile" in profile_names

    def test_get_flavor_profile(self, auth_token):
        """Test getting a specific flavor profile."""
        # Get profiles first to get an ID
        list_response = client.get(
            "/v2.0/lbaas/flavorprofiles", headers={"X-Auth-Token": auth_token}
        )
        profiles = list_response.json()["flavorprofiles"]
        profile_id = profiles[0]["id"]

        response = client.get(
            f"/v2.0/lbaas/flavorprofiles/{profile_id}", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "flavorprofile" in data
        assert data["flavorprofile"]["id"] == profile_id


class TestOctaviaAvailabilityZones:
    """Test Octavia availability zone endpoints."""

    def test_list_availability_zones(self, auth_token):
        """Test listing availability zones."""
        response = client.get("/v2.0/lbaas/availabilityzones", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "availabilityzones" in data
        assert len(data["availabilityzones"]) > 0

        # Check for expected zones
        zone_names = [zone["name"] for zone in data["availabilityzones"]]
        assert "nova" in zone_names

    def test_get_availability_zone(self, auth_token):
        """Test getting a specific availability zone."""
        response = client.get(
            "/v2.0/lbaas/availabilityzones/nova", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "availabilityzone" in data
        assert data["availabilityzone"]["name"] == "nova"
        assert data["availabilityzone"]["enabled"] is True

    def test_list_availability_zone_profiles(self, auth_token):
        """Test listing availability zone profiles."""
        response = client.get(
            "/v2.0/lbaas/availabilityzoneprofiles", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "availabilityzoneprofiles" in data
        assert len(data["availabilityzoneprofiles"]) > 0

    def test_get_availability_zone_profile(self, auth_token):
        """Test getting a specific availability zone profile."""
        # Get profiles first to get an ID
        list_response = client.get(
            "/v2.0/lbaas/availabilityzoneprofiles", headers={"X-Auth-Token": auth_token}
        )
        profiles = list_response.json()["availabilityzoneprofiles"]
        profile_id = profiles[0]["id"]

        response = client.get(
            f"/v2.0/lbaas/availabilityzoneprofiles/{profile_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "availabilityzoneprofile" in data
        assert data["availabilityzoneprofile"]["id"] == profile_id


class TestOctaviaAPIVersions:
    """Test API version endpoints compatibility."""

    def test_v2_endpoints_work(self, auth_token):
        """Test that v2 (without .0) endpoints work."""
        # Test quota endpoint with v2 path
        response = client.get("/v2/lbaas/quotas/test-project", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        # Test providers endpoint with v2 path
        response = client.get("/v2/lbaas/providers", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        # Test flavors endpoint with v2 path
        response = client.get("/v2/lbaas/flavors", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

    def test_v20_endpoints_work(self, auth_token):
        """Test that v2.0 endpoints work."""
        # Test quota endpoint with v2.0 path
        response = client.get(
            "/v2.0/lbaas/quotas/test-project", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        # Test providers endpoint with v2.0 path
        response = client.get("/v2.0/lbaas/providers", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200
