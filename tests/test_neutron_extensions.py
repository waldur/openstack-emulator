"""Test Neutron extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import grant_scope

# Create Neutron app for testing
service_apps = create_all_service_apps()
neutron_app = service_apps["neutron"]
client = TestClient(neutron_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._networks.clear()
    db._subnets.clear()
    db._ports.clear()
    db._routers.clear()
    db._floating_ips.clear()
    db._security_groups.clear()
    db._security_group_rules.clear()
    db._qos_policies.clear()
    db._neutron_agents.clear()
    db._trunks.clear()
    db._tokens.clear()
    db._init_default_neutron_data()
    db._init_neutron_extensions()
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


class TestNeutronExtensions:
    """Test Neutron extensions endpoints."""

    def test_list_extensions(self, auth_token):
        """Test listing Neutron extensions."""
        response = client.get("/v2.0/extensions", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "extensions" in data
        assert len(data["extensions"]) > 0

        # Check for specific extensions
        extension_aliases = [ext["alias"] for ext in data["extensions"]]
        assert "qos" in extension_aliases
        assert "agent" in extension_aliases
        assert "trunk" in extension_aliases

    def test_get_extension(self, auth_token):
        """Test getting a specific extension."""
        response = client.get("/v2.0/extensions/qos", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "extension" in data
        assert data["extension"]["alias"] == "qos"
        assert data["extension"]["name"] == "Quality of Service"

    def test_get_extension_not_found(self, auth_token):
        """Test getting a non-existent extension."""
        response = client.get("/v2.0/extensions/nonexistent", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 404


class TestQoSPolicies:
    """Test QoS policy endpoints."""

    def test_list_qos_policies_empty(self, auth_token):
        """Test listing QoS policies when none exist."""
        response = client.get("/v2.0/qos/policies", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "policies" in data
        assert data["policies"] == []

    def test_create_qos_policy(self, auth_token):
        """Test creating a QoS policy."""
        response = client.post(
            "/v2.0/qos/policies",
            json={
                "policy": {
                    "name": "test-policy",
                    "description": "Test QoS policy",
                    "shared": False,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "policy" in data
        assert data["policy"]["name"] == "test-policy"
        assert data["policy"]["description"] == "Test QoS policy"
        assert data["policy"]["shared"] is False

    def test_get_qos_policy(self, auth_token):
        """Test getting a QoS policy by ID."""
        # Create a policy first
        create_response = client.post(
            "/v2.0/qos/policies",
            json={"policy": {"name": "get-test-policy"}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Get the policy
        response = client.get(
            f"/v2.0/qos/policies/{policy_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["policy"]["id"] == policy_id
        assert data["policy"]["name"] == "get-test-policy"

    def test_update_qos_policy(self, auth_token):
        """Test updating a QoS policy."""
        # Create a policy first
        create_response = client.post(
            "/v2.0/qos/policies",
            json={"policy": {"name": "update-test-policy"}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Update the policy
        response = client.put(
            f"/v2.0/qos/policies/{policy_id}",
            json={
                "policy": {
                    "name": "updated-policy",
                    "description": "Updated description",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["policy"]["name"] == "updated-policy"
        assert data["policy"]["description"] == "Updated description"

    def test_delete_qos_policy(self, auth_token):
        """Test deleting a QoS policy."""
        # Create a policy first
        create_response = client.post(
            "/v2.0/qos/policies",
            json={"policy": {"name": "delete-test-policy"}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Delete the policy
        response = client.delete(
            f"/v2.0/qos/policies/{policy_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            f"/v2.0/qos/policies/{policy_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_list_qos_rule_types(self, auth_token):
        """Test listing QoS rule types."""
        response = client.get("/v2.0/qos/rule-types", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "rule_types" in data
        assert len(data["rule_types"]) > 0

        # Check for expected rule types
        rule_type_names = [rt["type"] for rt in data["rule_types"]]
        assert "bandwidth_limit" in rule_type_names
        assert "dscp_marking" in rule_type_names
        assert "minimum_bandwidth" in rule_type_names


class TestNeutronAgents:
    """Test Neutron agent endpoints."""

    def test_list_agents(self, auth_token):
        """Test listing Neutron agents."""
        response = client.get("/v2.0/agents", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) > 0  # Should have default agents

        # Check agent types
        agent_types = [agent["agent_type"] for agent in data["agents"]]
        assert "Open vSwitch agent" in agent_types
        assert "DHCP agent" in agent_types
        assert "L3 agent" in agent_types
        assert "Metadata agent" in agent_types

    def test_get_agent(self, auth_token):
        """Test getting a specific agent."""
        # List agents first to get an ID
        list_response = client.get("/v2.0/agents", headers={"X-Auth-Token": auth_token})
        agents = list_response.json()["agents"]
        agent_id = agents[0]["id"]

        # Get the specific agent
        response = client.get(
            f"/v2.0/agents/{agent_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "agent" in data
        assert data["agent"]["id"] == agent_id

    def test_update_agent(self, auth_token):
        """Test updating an agent."""
        # List agents first to get an ID
        list_response = client.get("/v2.0/agents", headers={"X-Auth-Token": auth_token})
        agents = list_response.json()["agents"]
        agent_id = agents[0]["id"]

        # Update the agent
        response = client.put(
            f"/v2.0/agents/{agent_id}",
            json={
                "agent": {
                    "admin_state_up": False,
                    "description": "Updated agent",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["agent"]["admin_state_up"] is False

    def test_filter_agents_by_type(self, auth_token):
        """Test filtering agents by type."""
        response = client.get(
            "/v2.0/agents?agent_type=DHCP agent",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) >= 1

        # All returned agents should be DHCP agents
        for agent in data["agents"]:
            assert agent["agent_type"] == "DHCP agent"


class TestTrunks:
    """Test trunk networking endpoints."""

    def test_list_trunks_empty(self, auth_token):
        """Test listing trunks when none exist."""
        response = client.get("/v2.0/trunks", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "trunks" in data
        assert data["trunks"] == []

    def test_create_trunk(self, auth_token):
        """Test creating a trunk."""
        # First create a network and port
        network_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "trunk-network"}},
            headers={"X-Auth-Token": auth_token},
        )
        network_id = network_response.json()["network"]["id"]

        port_response = client.post(
            "/v2.0/ports",
            json={"port": {"network_id": network_id, "name": "trunk-port"}},
            headers={"X-Auth-Token": auth_token},
        )
        port_id = port_response.json()["port"]["id"]

        # Create trunk
        response = client.post(
            "/v2.0/trunks",
            json={
                "trunk": {
                    "name": "test-trunk",
                    "port_id": port_id,
                    "description": "Test trunk",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "trunk" in data
        assert data["trunk"]["name"] == "test-trunk"
        assert data["trunk"]["port_id"] == port_id
        assert data["trunk"]["status"] == "ACTIVE"

    def test_get_trunk(self, auth_token):
        """Test getting a trunk by ID."""
        # Create a network, port, and trunk first
        network_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "get-trunk-network"}},
            headers={"X-Auth-Token": auth_token},
        )
        network_id = network_response.json()["network"]["id"]

        port_response = client.post(
            "/v2.0/ports",
            json={"port": {"network_id": network_id, "name": "get-trunk-port"}},
            headers={"X-Auth-Token": auth_token},
        )
        port_id = port_response.json()["port"]["id"]

        create_response = client.post(
            "/v2.0/trunks",
            json={"trunk": {"name": "get-test-trunk", "port_id": port_id}},
            headers={"X-Auth-Token": auth_token},
        )
        trunk_id = create_response.json()["trunk"]["id"]

        # Get the trunk
        response = client.get(
            f"/v2.0/trunks/{trunk_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["trunk"]["id"] == trunk_id
        assert data["trunk"]["name"] == "get-test-trunk"

    def test_update_trunk(self, auth_token):
        """Test updating a trunk."""
        # Create a network, port, and trunk first
        network_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "update-trunk-network"}},
            headers={"X-Auth-Token": auth_token},
        )
        network_id = network_response.json()["network"]["id"]

        port_response = client.post(
            "/v2.0/ports",
            json={"port": {"network_id": network_id, "name": "update-trunk-port"}},
            headers={"X-Auth-Token": auth_token},
        )
        port_id = port_response.json()["port"]["id"]

        create_response = client.post(
            "/v2.0/trunks",
            json={"trunk": {"name": "update-test-trunk", "port_id": port_id}},
            headers={"X-Auth-Token": auth_token},
        )
        trunk_id = create_response.json()["trunk"]["id"]

        # Update the trunk
        response = client.put(
            f"/v2.0/trunks/{trunk_id}",
            json={
                "trunk": {
                    "name": "updated-trunk",
                    "description": "Updated description",
                    "admin_state_up": False,
                    "port_id": port_id,  # Required field
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["trunk"]["name"] == "updated-trunk"
        assert data["trunk"]["description"] == "Updated description"
        assert data["trunk"]["admin_state_up"] is False

    def test_delete_trunk(self, auth_token):
        """Test deleting a trunk."""
        # Create a network, port, and trunk first
        network_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "delete-trunk-network"}},
            headers={"X-Auth-Token": auth_token},
        )
        network_id = network_response.json()["network"]["id"]

        port_response = client.post(
            "/v2.0/ports",
            json={"port": {"network_id": network_id, "name": "delete-trunk-port"}},
            headers={"X-Auth-Token": auth_token},
        )
        port_id = port_response.json()["port"]["id"]

        create_response = client.post(
            "/v2.0/trunks",
            json={"trunk": {"name": "delete-test-trunk", "port_id": port_id}},
            headers={"X-Auth-Token": auth_token},
        )
        trunk_id = create_response.json()["trunk"]["id"]

        # Delete the trunk
        response = client.delete(
            f"/v2.0/trunks/{trunk_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            f"/v2.0/trunks/{trunk_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestTenantIsolation:
    """Test tenant isolation for new Neutron features."""

    def test_qos_policy_tenant_isolation(self, auth_token):
        """Test that QoS policies are properly isolated by tenant."""
        # Create a policy in the admin project
        create_response = client.post(
            "/v2.0/qos/policies",
            json={"policy": {"name": "admin-policy", "shared": False}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Create a different project and get token
        keystone_app = create_all_service_apps()["keystone"]
        keystone_client = TestClient(keystone_app)

        _project_response = keystone_client.post(
            "/v3/projects",
            json={
                "project": {
                    "name": "qos-test-project",
                    "domain_id": "default",
                    "description": "Test project for QoS isolation",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )

        grant_scope(project_name="qos-test-project")
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
                    "scope": {"project": {"name": "qos-test-project", "domain": {"id": "default"}}},
                }
            },
        )
        other_token = other_token_response.headers["X-Subject-Token"]

        # Try to access the policy with the other project's token
        response = client.get(
            f"/v2.0/qos/policies/{policy_id}",
            headers={"X-Auth-Token": other_token},
        )
        assert response.status_code == 404  # Should not be accessible


class TestNeutronFlavors:
    """Test Neutron service flavor endpoints."""

    def test_list_neutron_flavors(self, auth_token):
        """Test listing Neutron service flavors."""
        response = client.get("/v2.0/flavors", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "flavors" in data
        assert len(data["flavors"]) > 0  # Should have default flavors

        # Check for expected flavors
        flavor_names = [flavor["name"] for flavor in data["flavors"]]
        assert "default-router" in flavor_names
        assert "ha-router" in flavor_names
        assert "default-loadbalancer" in flavor_names

    def test_get_neutron_flavor(self, auth_token):
        """Test getting a specific Neutron flavor."""
        # List flavors first to get an ID
        list_response = client.get("/v2.0/flavors", headers={"X-Auth-Token": auth_token})
        flavors = list_response.json()["flavors"]
        flavor_id = flavors[0]["id"]

        # Get the specific flavor
        response = client.get(f"/v2.0/flavors/{flavor_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "flavor" in data
        assert data["flavor"]["id"] == flavor_id

    def test_create_neutron_flavor(self, auth_token):
        """Test creating a Neutron service flavor."""
        response = client.post(
            "/v2.0/flavors",
            json={
                "flavor": {
                    "name": "test-router-flavor",
                    "description": "Test router service flavor",
                    "service_type": "L3_ROUTER_NAT",
                    "enabled": True,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "flavor" in data
        assert data["flavor"]["name"] == "test-router-flavor"
        assert data["flavor"]["service_type"] == "L3_ROUTER_NAT"
        assert data["flavor"]["enabled"] is True

    def test_filter_flavors_by_service_type(self, auth_token):
        """Test filtering flavors by service type."""
        response = client.get(
            "/v2.0/flavors?service_type=L3_ROUTER_NAT",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "flavors" in data

        # All returned flavors should be router flavors
        for flavor in data["flavors"]:
            assert flavor["service_type"] == "L3_ROUTER_NAT"

    def test_list_service_profiles(self, auth_token):
        """Test listing service profiles."""
        response = client.get("/v2.0/service_profiles", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "service_profiles" in data
        assert len(data["service_profiles"]) > 0  # Should have default profiles

        # Check for expected profiles
        profile_descriptions = [profile["description"] for profile in data["service_profiles"]]
        router_profiles = [desc for desc in profile_descriptions if "router" in desc.lower()]
        assert len(router_profiles) >= 2  # Should have default and HA router profiles


class TestTenantProjectScoping:
    """Project-id scoping and cloud-admin cross-project access.

    The admin project (Waldur's admin session) may act across projects;
    tenant-scoped tokens stay isolated. Covers on-behalf-of creation, by-id
    cross-project access, list scoping, and RBAC ownership.
    """

    def _tenant(self, name):
        """Create a project and a token scoped to it; return (project_id, token)."""
        proj = grant_scope(project_name=name)
        token = db.create_token(project_name=name, project_id=proj.id)
        return proj.id, token.id

    def _admin(self):
        return db.create_token(project_name="admin").id

    def test_create_on_behalf_of_tenant(self):
        """Admin may create a resource owned by another project via the body."""
        pid, _ = self._tenant("scope-create")
        admin = self._admin()
        resp = client.post(
            "/v2.0/networks",
            json={"network": {"name": "oa-net", "project_id": pid}},
            headers={"X-Auth-Token": admin},
        )
        assert resp.status_code == 201
        assert resp.json()["network"]["project_id"] == pid

    def test_admin_cross_project_by_id(self):
        """Admin reaches any project's resource by id; other tenants cannot."""
        _, tok_a = self._tenant("scope-a")
        _, tok_b = self._tenant("scope-b")
        admin = self._admin()
        net = client.post(
            "/v2.0/networks",
            json={"network": {"name": "a-net"}},
            headers={"X-Auth-Token": tok_a},
        ).json()["network"]
        nid = net["id"]

        # Owner and admin can read it; the other tenant cannot.
        assert (
            client.get(f"/v2.0/networks/{nid}", headers={"X-Auth-Token": tok_a}).status_code == 200
        )
        assert (
            client.get(f"/v2.0/networks/{nid}", headers={"X-Auth-Token": admin}).status_code == 200
        )
        assert (
            client.get(f"/v2.0/networks/{nid}", headers={"X-Auth-Token": tok_b}).status_code == 404
        )
        # Admin can delete cross-project.
        assert (
            client.delete(f"/v2.0/networks/{nid}", headers={"X-Auth-Token": admin}).status_code
            == 204
        )

    def test_list_scoping(self):
        """Tenant lists are scoped; admin spans all and honors tenant_id."""
        pid_a, tok_a = self._tenant("scope-la")
        _, tok_b = self._tenant("scope-lb")
        admin = self._admin()
        na = client.post(
            "/v2.0/networks",
            json={"network": {"name": "la-net"}},
            headers={"X-Auth-Token": tok_a},
        ).json()["network"]["id"]
        nb = client.post(
            "/v2.0/networks",
            json={"network": {"name": "lb-net"}},
            headers={"X-Auth-Token": tok_b},
        ).json()["network"]["id"]

        a_ids = [
            n["id"]
            for n in client.get("/v2.0/networks", headers={"X-Auth-Token": tok_a}).json()[
                "networks"
            ]
        ]
        assert na in a_ids and nb not in a_ids

        admin_ids = [
            n["id"]
            for n in client.get("/v2.0/networks", headers={"X-Auth-Token": admin}).json()[
                "networks"
            ]
        ]
        assert na in admin_ids and nb in admin_ids

        filtered = [
            n["id"]
            for n in client.get(
                "/v2.0/networks",
                params={"tenant_id": pid_a},
                headers={"X-Auth-Token": admin},
            ).json()["networks"]
        ]
        assert na in filtered and nb not in filtered

    def test_admin_can_update_other_project_port(self):
        """Admin (admin project) may update a tenant's port by id; peers cannot.

        Covers Waldur's admin-session port operations (e.g. port security).
        """
        _, tok_a = self._tenant("scope-upd-a")
        _, tok_b = self._tenant("scope-upd-b")
        admin = self._admin()
        net = client.post(
            "/v2.0/networks",
            json={"network": {"name": "upd-net"}},
            headers={"X-Auth-Token": tok_a},
        ).json()["network"]
        port = client.post(
            "/v2.0/ports",
            json={"port": {"name": "upd-port", "network_id": net["id"]}},
            headers={"X-Auth-Token": tok_a},
        ).json()["port"]
        pid = port["id"]

        ok = client.put(
            f"/v2.0/ports/{pid}",
            json={"port": {"port_security_enabled": False}},
            headers={"X-Auth-Token": admin},
        )
        assert ok.status_code == 200
        assert ok.json()["port"]["port_security_enabled"] is False

        denied = client.put(
            f"/v2.0/ports/{pid}",
            json={"port": {"name": "hijacked"}},
            headers={"X-Auth-Token": tok_b},
        )
        assert denied.status_code == 404

    def test_rbac_owner_is_object_project(self):
        """An admin-created RBAC policy is owned by the shared object's project."""
        pid_a, tok_a = self._tenant("scope-rbac")
        admin = self._admin()
        net = client.post(
            "/v2.0/networks",
            json={"network": {"name": "rbac-net"}},
            headers={"X-Auth-Token": tok_a},
        ).json()["network"]
        resp = client.post(
            "/v2.0/rbac-policies",
            json={
                "rbac_policy": {
                    "object_type": "network",
                    "object_id": net["id"],
                    "target_tenant": "*",
                    "action": "access_as_shared",
                }
            },
            headers={"X-Auth-Token": admin},
        )
        assert resp.status_code == 201
        assert resp.json()["rbac_policy"]["project_id"] == pid_a
