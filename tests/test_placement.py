"""Tests for the Placement API emulator."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test so placement and Nova state are clean."""
    db._servers.clear()
    db._tokens.clear()
    db._resource_providers.clear()
    db._init_default_flavors()
    db._init_default_resource_providers()
    db.reset_keystone()
    yield


@pytest.fixture
def client():
    """Create test client for the placement service."""
    apps = create_all_service_apps()
    return TestClient(apps["placement"])


@pytest.fixture
def auth_token():
    """Mint a token directly in the database."""
    token = db.create_token(user_name="admin", project_name="admin", domain_id="default")
    return token.id


@pytest.fixture
def provider_uuid() -> str:
    """Return the UUID of the seeded default resource provider."""
    providers = db.list_resource_providers()
    assert providers, "expected at least one seeded resource provider"
    return providers[0].uuid


class TestVersions:
    def test_get_versions(self, client):
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert "versions" in body
        assert body["versions"][0]["id"] == "v1.0"
        assert body["versions"][0]["min_version"] == "1.0"


class TestAuthentication:
    def test_resource_providers_requires_token(self, client):
        response = client.get("/resource_providers")
        assert response.status_code == 401

    def test_inventories_requires_token(self, client, provider_uuid):
        response = client.get(f"/resource_providers/{provider_uuid}/inventories")
        assert response.status_code == 401


class TestResourceProviders:
    def test_list_returns_default_provider(self, client, auth_token):
        response = client.get("/resource_providers", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200
        body = response.json()
        assert "resource_providers" in body
        assert len(body["resource_providers"]) == 1
        provider = body["resource_providers"][0]
        assert provider["name"] == "compute-host-1"
        assert provider["uuid"]
        assert provider["root_provider_uuid"] == provider["uuid"]
        assert provider["parent_provider_uuid"] is None

    def test_list_filter_by_name(self, client, auth_token):
        response = client.get(
            "/resource_providers?name=compute-host-1",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert len(response.json()["resource_providers"]) == 1

        response = client.get(
            "/resource_providers?name=does-not-exist",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["resource_providers"] == []

    def test_get_single_provider(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["uuid"] == provider_uuid
        assert body["name"] == "compute-host-1"

    def test_get_unknown_provider_404(self, client, auth_token):
        response = client.get(
            "/resource_providers/00000000-0000-0000-0000-000000000000",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestInventories:
    def test_inventories_shape(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}/inventories",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        body = response.json()
        assert "resource_provider_generation" in body
        inventories = body["inventories"]
        for resource_class in ("VCPU", "MEMORY_MB", "DISK_GB"):
            assert resource_class in inventories
            entry = inventories[resource_class]
            assert entry["total"] > 0
            assert "reserved" in entry
            assert "allocation_ratio" in entry
            assert entry["min_unit"] == 1


class TestUsages:
    def test_usages_zero_when_no_servers(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}/usages",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        usages = response.json()["usages"]
        assert usages == {"VCPU": 0, "MEMORY_MB": 0, "DISK_GB": 0}

    def test_usages_reflect_running_servers(self, client, auth_token, provider_uuid):
        # Spin up a server using the m1.small flavor (1 vcpu, 2048 MB ram, 20 GB disk).
        db.create_server(
            name="test-vm",
            flavor_id="2",
            image_id="any",
            tenant_id="some-tenant",
            user_id="some-user",
        )
        response = client.get(
            f"/resource_providers/{provider_uuid}/usages",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        usages = response.json()["usages"]
        assert usages["VCPU"] == 1
        assert usages["MEMORY_MB"] == 2048
        assert usages["DISK_GB"] == 20


class TestStubs:
    def test_aggregates_empty(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}/aggregates",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["aggregates"] == []

    def test_traits_empty(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}/traits",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["traits"] == []

    def test_allocations_empty(self, client, auth_token, provider_uuid):
        response = client.get(
            f"/resource_providers/{provider_uuid}/allocations",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["allocations"] == {}


class TestServiceCatalog:
    def test_placement_advertised_in_catalog(self):
        catalog = db._generate_service_catalog("http://localhost", project_id="p1")
        types = [entry["type"] for entry in catalog]
        assert "placement" in types
        placement = next(entry for entry in catalog if entry["type"] == "placement")
        assert placement["name"] == "placement"
        urls = [ep["url"] for ep in placement["endpoints"]]
        assert all(url.endswith(":8778") for url in urls)
