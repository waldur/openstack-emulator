"""Tests for Octavia Load Balancer API emulator."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    db.reset_octavia()
    yield


# Create the app once at module level
_apps = create_all_service_apps()
client = TestClient(_apps["octavia"])


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "octavia"


class TestVersions:
    """Test API versions endpoint."""

    def test_get_versions(self):
        """Test getting API versions."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) > 0


class TestLoadBalancers:
    """Test load balancer CRUD operations."""

    def test_list_loadbalancers_empty(self):
        """Test listing load balancers when empty."""
        response = client.get("/v2.0/lbaas/loadbalancers")
        assert response.status_code == 200
        data = response.json()
        assert "loadbalancers" in data
        assert len(data["loadbalancers"]) == 0

    def test_create_loadbalancer(self):
        """Test creating a load balancer."""
        response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={
                "loadbalancer": {
                    "name": "test-lb",
                    "description": "Test load balancer",
                    "admin_state_up": True,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["loadbalancer"]["name"] == "test-lb"
        assert data["loadbalancer"]["description"] == "Test load balancer"
        assert data["loadbalancer"]["admin_state_up"] is True
        assert data["loadbalancer"]["provisioning_status"] == "ACTIVE"
        assert data["loadbalancer"]["operating_status"] == "ONLINE"
        assert "vip_address" in data["loadbalancer"]

    def test_get_loadbalancer(self):
        """Test getting a specific load balancer."""
        # Create a load balancer first
        create_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "get-test"}},
        )
        lb_id = create_response.json()["loadbalancer"]["id"]

        response = client.get(f"/v2.0/lbaas/loadbalancers/{lb_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["loadbalancer"]["id"] == lb_id
        assert data["loadbalancer"]["name"] == "get-test"

    def test_get_loadbalancer_not_found(self):
        """Test getting non-existent load balancer."""
        response = client.get("/v2.0/lbaas/loadbalancers/non-existent-id")
        assert response.status_code == 404

    def test_update_loadbalancer(self):
        """Test updating a load balancer."""
        # Create a load balancer first
        create_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "update-test"}},
        )
        lb_id = create_response.json()["loadbalancer"]["id"]

        # Update the load balancer
        response = client.put(
            f"/v2.0/lbaas/loadbalancers/{lb_id}",
            json={
                "loadbalancer": {
                    "name": "updated-lb",
                    "description": "Updated description",
                    "admin_state_up": False,
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["loadbalancer"]["name"] == "updated-lb"
        assert data["loadbalancer"]["description"] == "Updated description"
        assert data["loadbalancer"]["admin_state_up"] is False

    def test_delete_loadbalancer(self):
        """Test deleting a load balancer."""
        # Create a load balancer first
        create_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "delete-test"}},
        )
        lb_id = create_response.json()["loadbalancer"]["id"]

        # Delete the load balancer
        response = client.delete(f"/v2.0/lbaas/loadbalancers/{lb_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/loadbalancers/{lb_id}")
        assert get_response.status_code == 404

    def test_get_loadbalancer_stats(self):
        """Test getting load balancer statistics."""
        # Create a load balancer first
        create_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "stats-test"}},
        )
        lb_id = create_response.json()["loadbalancer"]["id"]

        response = client.get(f"/v2.0/lbaas/loadbalancers/{lb_id}/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert "bytes_in" in data["stats"]
        assert "bytes_out" in data["stats"]

    def test_get_loadbalancer_status(self):
        """Test getting load balancer status tree."""
        # Create a load balancer first
        create_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "status-test"}},
        )
        lb_id = create_response.json()["loadbalancer"]["id"]

        response = client.get(f"/v2.0/lbaas/loadbalancers/{lb_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "loadbalancer" in data["statuses"]


class TestListeners:
    """Test listener CRUD operations."""

    def test_list_listeners_empty(self):
        """Test listing listeners when empty."""
        response = client.get("/v2.0/lbaas/listeners")
        assert response.status_code == 200
        data = response.json()
        assert "listeners" in data
        assert len(data["listeners"]) == 0

    def test_create_listener(self):
        """Test creating a listener."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "listener-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create listener
        response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "test-listener",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["listener"]["name"] == "test-listener"
        assert data["listener"]["protocol"] == "HTTP"
        assert data["listener"]["protocol_port"] == 80

    def test_get_listener(self):
        """Test getting a specific listener."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "get-listener-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create listener
        create_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "get-test",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        listener_id = create_response.json()["listener"]["id"]

        response = client.get(f"/v2.0/lbaas/listeners/{listener_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["listener"]["id"] == listener_id

    def test_update_listener(self):
        """Test updating a listener."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "update-listener-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create listener
        create_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "update-test",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        listener_id = create_response.json()["listener"]["id"]

        # Update it
        response = client.put(
            f"/v2.0/lbaas/listeners/{listener_id}",
            json={"listener": {"name": "updated-listener", "connection_limit": 1000}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["listener"]["name"] == "updated-listener"
        assert data["listener"]["connection_limit"] == 1000

    def test_delete_listener(self):
        """Test deleting a listener."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "delete-listener-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create listener
        create_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "delete-test",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        listener_id = create_response.json()["listener"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/lbaas/listeners/{listener_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/listeners/{listener_id}")
        assert get_response.status_code == 404


class TestPools:
    """Test pool CRUD operations."""

    def test_list_pools_empty(self):
        """Test listing pools when empty."""
        response = client.get("/v2.0/lbaas/pools")
        assert response.status_code == 200
        data = response.json()
        assert "pools" in data
        assert len(data["pools"]) == 0

    def test_create_pool(self):
        """Test creating a pool."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "pool-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create pool
        response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "test-pool",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["pool"]["name"] == "test-pool"
        assert data["pool"]["protocol"] == "HTTP"
        assert data["pool"]["lb_algorithm"] == "ROUND_ROBIN"

    def test_get_pool(self):
        """Test getting a specific pool."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "get-pool-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create pool
        create_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "get-test",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        pool_id = create_response.json()["pool"]["id"]

        response = client.get(f"/v2.0/lbaas/pools/{pool_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["pool"]["id"] == pool_id

    def test_update_pool(self):
        """Test updating a pool."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "update-pool-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create pool
        create_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "update-test",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        pool_id = create_response.json()["pool"]["id"]

        # Update it
        response = client.put(
            f"/v2.0/lbaas/pools/{pool_id}",
            json={"pool": {"name": "updated-pool", "lb_algorithm": "LEAST_CONNECTIONS"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pool"]["name"] == "updated-pool"
        assert data["pool"]["lb_algorithm"] == "LEAST_CONNECTIONS"

    def test_delete_pool(self):
        """Test deleting a pool."""
        # Create a load balancer first
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "delete-pool-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create pool
        create_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "delete-test",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        pool_id = create_response.json()["pool"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/lbaas/pools/{pool_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/pools/{pool_id}")
        assert get_response.status_code == 404


class TestMembers:
    """Test pool member CRUD operations."""

    @pytest.fixture
    def pool_id(self):
        """Create a pool for testing members."""
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "member-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        pool_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "member-pool",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        return pool_response.json()["pool"]["id"]

    def test_list_members_empty(self, pool_id):
        """Test listing members when empty."""
        response = client.get(f"/v2.0/lbaas/pools/{pool_id}/members")
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert len(data["members"]) == 0

    def test_create_member(self, pool_id):
        """Test creating a pool member."""
        response = client.post(
            f"/v2.0/lbaas/pools/{pool_id}/members",
            json={
                "member": {
                    "name": "test-member",
                    "address": "192.168.1.10",
                    "protocol_port": 8080,
                    "weight": 5,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["member"]["name"] == "test-member"
        assert data["member"]["address"] == "192.168.1.10"
        assert data["member"]["protocol_port"] == 8080
        assert data["member"]["weight"] == 5

    def test_get_member(self, pool_id):
        """Test getting a specific member."""
        create_response = client.post(
            f"/v2.0/lbaas/pools/{pool_id}/members",
            json={
                "member": {
                    "name": "get-test",
                    "address": "192.168.1.11",
                    "protocol_port": 8080,
                }
            },
        )
        member_id = create_response.json()["member"]["id"]

        response = client.get(f"/v2.0/lbaas/pools/{pool_id}/members/{member_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["member"]["id"] == member_id

    def test_update_member(self, pool_id):
        """Test updating a member."""
        create_response = client.post(
            f"/v2.0/lbaas/pools/{pool_id}/members",
            json={
                "member": {
                    "name": "update-test",
                    "address": "192.168.1.12",
                    "protocol_port": 8080,
                    "weight": 1,
                }
            },
        )
        member_id = create_response.json()["member"]["id"]

        response = client.put(
            f"/v2.0/lbaas/pools/{pool_id}/members/{member_id}",
            json={"member": {"name": "updated-member", "weight": 10}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["member"]["name"] == "updated-member"
        assert data["member"]["weight"] == 10

    def test_delete_member(self, pool_id):
        """Test deleting a member."""
        create_response = client.post(
            f"/v2.0/lbaas/pools/{pool_id}/members",
            json={
                "member": {
                    "name": "delete-test",
                    "address": "192.168.1.13",
                    "protocol_port": 8080,
                }
            },
        )
        member_id = create_response.json()["member"]["id"]

        response = client.delete(f"/v2.0/lbaas/pools/{pool_id}/members/{member_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/pools/{pool_id}/members/{member_id}")
        assert get_response.status_code == 404


class TestHealthMonitors:
    """Test health monitor CRUD operations."""

    @pytest.fixture
    def pool_id(self):
        """Create a pool for testing health monitors."""
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "hm-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        pool_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "hm-pool",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        return pool_response.json()["pool"]["id"]

    def test_list_healthmonitors_empty(self):
        """Test listing health monitors when empty."""
        response = client.get("/v2.0/lbaas/healthmonitors")
        assert response.status_code == 200
        data = response.json()
        assert "healthmonitors" in data
        assert len(data["healthmonitors"]) == 0

    def test_create_healthmonitor(self, pool_id):
        """Test creating a health monitor."""
        response = client.post(
            "/v2.0/lbaas/healthmonitors",
            json={
                "healthmonitor": {
                    "name": "test-hm",
                    "type": "HTTP",
                    "delay": 5,
                    "timeout": 3,
                    "max_retries": 3,
                    "pool_id": pool_id,
                    "url_path": "/health",
                    "expected_codes": "200,201",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["healthmonitor"]["name"] == "test-hm"
        assert data["healthmonitor"]["type"] == "HTTP"
        assert data["healthmonitor"]["delay"] == 5
        assert data["healthmonitor"]["timeout"] == 3
        assert data["healthmonitor"]["url_path"] == "/health"

    def test_get_healthmonitor(self, pool_id):
        """Test getting a specific health monitor."""
        create_response = client.post(
            "/v2.0/lbaas/healthmonitors",
            json={
                "healthmonitor": {
                    "name": "get-test",
                    "type": "HTTP",
                    "delay": 5,
                    "timeout": 3,
                    "max_retries": 3,
                    "pool_id": pool_id,
                }
            },
        )
        hm_id = create_response.json()["healthmonitor"]["id"]

        response = client.get(f"/v2.0/lbaas/healthmonitors/{hm_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["healthmonitor"]["id"] == hm_id

    def test_update_healthmonitor(self, pool_id):
        """Test updating a health monitor."""
        create_response = client.post(
            "/v2.0/lbaas/healthmonitors",
            json={
                "healthmonitor": {
                    "name": "update-test",
                    "type": "HTTP",
                    "delay": 5,
                    "timeout": 3,
                    "max_retries": 3,
                    "pool_id": pool_id,
                }
            },
        )
        hm_id = create_response.json()["healthmonitor"]["id"]

        response = client.put(
            f"/v2.0/lbaas/healthmonitors/{hm_id}",
            json={
                "healthmonitor": {
                    "name": "updated-hm",
                    "delay": 10,
                    "timeout": 5,
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["healthmonitor"]["name"] == "updated-hm"
        assert data["healthmonitor"]["delay"] == 10
        assert data["healthmonitor"]["timeout"] == 5

    def test_delete_healthmonitor(self, pool_id):
        """Test deleting a health monitor."""
        create_response = client.post(
            "/v2.0/lbaas/healthmonitors",
            json={
                "healthmonitor": {
                    "name": "delete-test",
                    "type": "HTTP",
                    "delay": 5,
                    "timeout": 3,
                    "max_retries": 3,
                    "pool_id": pool_id,
                }
            },
        )
        hm_id = create_response.json()["healthmonitor"]["id"]

        response = client.delete(f"/v2.0/lbaas/healthmonitors/{hm_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/healthmonitors/{hm_id}")
        assert get_response.status_code == 404


class TestL7Policies:
    """Test L7 policy CRUD operations."""

    @pytest.fixture
    def listener_id(self):
        """Create a listener for testing L7 policies."""
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "l7-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        listener_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "l7-listener",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        return listener_response.json()["listener"]["id"]

    def test_list_l7policies_empty(self):
        """Test listing L7 policies when empty."""
        response = client.get("/v2.0/lbaas/l7policies")
        assert response.status_code == 200
        data = response.json()
        assert "l7policies" in data
        assert len(data["l7policies"]) == 0

    def test_create_l7policy(self, listener_id):
        """Test creating an L7 policy."""
        response = client.post(
            "/v2.0/lbaas/l7policies",
            json={
                "l7policy": {
                    "name": "test-policy",
                    "action": "REJECT",
                    "listener_id": listener_id,
                    "position": 1,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["l7policy"]["name"] == "test-policy"
        assert data["l7policy"]["action"] == "REJECT"

    def test_get_l7policy(self, listener_id):
        """Test getting a specific L7 policy."""
        create_response = client.post(
            "/v2.0/lbaas/l7policies",
            json={
                "l7policy": {
                    "name": "get-test",
                    "action": "REJECT",
                    "listener_id": listener_id,
                }
            },
        )
        policy_id = create_response.json()["l7policy"]["id"]

        response = client.get(f"/v2.0/lbaas/l7policies/{policy_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["l7policy"]["id"] == policy_id

    def test_update_l7policy(self, listener_id):
        """Test updating an L7 policy."""
        create_response = client.post(
            "/v2.0/lbaas/l7policies",
            json={
                "l7policy": {
                    "name": "update-test",
                    "action": "REJECT",
                    "listener_id": listener_id,
                }
            },
        )
        policy_id = create_response.json()["l7policy"]["id"]

        response = client.put(
            f"/v2.0/lbaas/l7policies/{policy_id}",
            json={
                "l7policy": {
                    "name": "updated-policy",
                    "action": "REDIRECT_TO_URL",
                    "redirect_url": "https://example.com",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["l7policy"]["name"] == "updated-policy"
        assert data["l7policy"]["action"] == "REDIRECT_TO_URL"

    def test_delete_l7policy(self, listener_id):
        """Test deleting an L7 policy."""
        create_response = client.post(
            "/v2.0/lbaas/l7policies",
            json={
                "l7policy": {
                    "name": "delete-test",
                    "action": "REJECT",
                    "listener_id": listener_id,
                }
            },
        )
        policy_id = create_response.json()["l7policy"]["id"]

        response = client.delete(f"/v2.0/lbaas/l7policies/{policy_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/l7policies/{policy_id}")
        assert get_response.status_code == 404


class TestL7Rules:
    """Test L7 rule CRUD operations."""

    @pytest.fixture
    def l7policy_id(self):
        """Create an L7 policy for testing L7 rules."""
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "rule-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        listener_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "rule-listener",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        listener_id = listener_response.json()["listener"]["id"]

        policy_response = client.post(
            "/v2.0/lbaas/l7policies",
            json={
                "l7policy": {
                    "name": "rule-policy",
                    "action": "REJECT",
                    "listener_id": listener_id,
                }
            },
        )
        return policy_response.json()["l7policy"]["id"]

    def test_list_l7rules_empty(self, l7policy_id):
        """Test listing L7 rules when empty."""
        response = client.get(f"/v2.0/lbaas/l7policies/{l7policy_id}/rules")
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert len(data["rules"]) == 0

    def test_create_l7rule(self, l7policy_id):
        """Test creating an L7 rule."""
        response = client.post(
            f"/v2.0/lbaas/l7policies/{l7policy_id}/rules",
            json={
                "rule": {
                    "type": "PATH",
                    "compare_type": "STARTS_WITH",
                    "value": "/api",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["rule"]["type"] == "PATH"
        assert data["rule"]["compare_type"] == "STARTS_WITH"
        assert data["rule"]["value"] == "/api"

    def test_get_l7rule(self, l7policy_id):
        """Test getting a specific L7 rule."""
        create_response = client.post(
            f"/v2.0/lbaas/l7policies/{l7policy_id}/rules",
            json={
                "rule": {
                    "type": "PATH",
                    "compare_type": "EQUAL_TO",
                    "value": "/health",
                }
            },
        )
        rule_id = create_response.json()["rule"]["id"]

        response = client.get(f"/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["rule"]["id"] == rule_id

    def test_update_l7rule(self, l7policy_id):
        """Test updating an L7 rule."""
        create_response = client.post(
            f"/v2.0/lbaas/l7policies/{l7policy_id}/rules",
            json={
                "rule": {
                    "type": "PATH",
                    "compare_type": "EQUAL_TO",
                    "value": "/old",
                }
            },
        )
        rule_id = create_response.json()["rule"]["id"]

        response = client.put(
            f"/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}",
            json={
                "rule": {
                    "value": "/new",
                    "invert": True,
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rule"]["value"] == "/new"
        assert data["rule"]["invert"] is True

    def test_delete_l7rule(self, l7policy_id):
        """Test deleting an L7 rule."""
        create_response = client.post(
            f"/v2.0/lbaas/l7policies/{l7policy_id}/rules",
            json={
                "rule": {
                    "type": "PATH",
                    "compare_type": "EQUAL_TO",
                    "value": "/delete",
                }
            },
        )
        rule_id = create_response.json()["rule"]["id"]

        response = client.delete(f"/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
        assert get_response.status_code == 404


class TestCascadeDelete:
    """Test cascade delete functionality."""

    def test_cascade_delete_loadbalancer(self):
        """Test cascade delete removes all child resources."""
        # Create load balancer
        lb_response = client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "cascade-lb"}},
        )
        lb_id = lb_response.json()["loadbalancer"]["id"]

        # Create listener
        listener_response = client.post(
            "/v2.0/lbaas/listeners",
            json={
                "listener": {
                    "name": "cascade-listener",
                    "protocol": "HTTP",
                    "protocol_port": 80,
                    "loadbalancer_id": lb_id,
                }
            },
        )
        listener_id = listener_response.json()["listener"]["id"]

        # Create pool
        pool_response = client.post(
            "/v2.0/lbaas/pools",
            json={
                "pool": {
                    "name": "cascade-pool",
                    "protocol": "HTTP",
                    "lb_algorithm": "ROUND_ROBIN",
                    "loadbalancer_id": lb_id,
                }
            },
        )
        pool_id = pool_response.json()["pool"]["id"]

        # Cascade delete
        response = client.delete(f"/v2.0/lbaas/loadbalancers/{lb_id}?cascade=true")
        assert response.status_code == 204

        # Verify all are gone
        assert client.get(f"/v2.0/lbaas/loadbalancers/{lb_id}").status_code == 404
        assert client.get(f"/v2.0/lbaas/listeners/{listener_id}").status_code == 404
        assert client.get(f"/v2.0/lbaas/pools/{pool_id}").status_code == 404
