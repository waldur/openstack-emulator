"""Tests for Neutron Networking API emulator."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.app_neutron import app
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    db.reset_neutron()
    yield


client = TestClient(app)


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "neutron"


class TestVersions:
    """Test API versions endpoint."""

    def test_get_versions(self):
        """Test getting API versions."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) > 0


class TestNetworks:
    """Test network CRUD operations."""

    def test_list_networks(self):
        """Test listing networks."""
        response = client.get("/v2.0/networks")
        assert response.status_code == 200
        data = response.json()
        assert "networks" in data
        # Default networks should exist
        assert len(data["networks"]) >= 2

    def test_create_network(self):
        """Test creating a network."""
        response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "test-network", "admin_state_up": True}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["network"]["name"] == "test-network"
        assert data["network"]["admin_state_up"] is True
        assert data["network"]["status"] == "ACTIVE"

    def test_get_network(self):
        """Test getting a specific network."""
        # First list to get a network ID
        list_response = client.get("/v2.0/networks")
        networks = list_response.json()["networks"]
        network_id = networks[0]["id"]

        response = client.get(f"/v2.0/networks/{network_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["network"]["id"] == network_id

    def test_get_network_not_found(self):
        """Test getting non-existent network."""
        response = client.get("/v2.0/networks/non-existent-id")
        assert response.status_code == 404

    def test_update_network(self):
        """Test updating a network."""
        # Create a network first
        create_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "update-test"}},
        )
        network_id = create_response.json()["network"]["id"]

        # Update the network
        response = client.put(
            f"/v2.0/networks/{network_id}",
            json={"network": {"name": "updated-network", "admin_state_up": False}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["network"]["name"] == "updated-network"
        assert data["network"]["admin_state_up"] is False

    def test_delete_network(self):
        """Test deleting a network."""
        # Create a network first
        create_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "delete-test"}},
        )
        network_id = create_response.json()["network"]["id"]

        # Delete the network
        response = client.delete(f"/v2.0/networks/{network_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/networks/{network_id}")
        assert get_response.status_code == 404


class TestSubnets:
    """Test subnet CRUD operations."""

    def test_list_subnets(self):
        """Test listing subnets."""
        response = client.get("/v2.0/subnets")
        assert response.status_code == 200
        data = response.json()
        assert "subnets" in data
        # Default subnets should exist
        assert len(data["subnets"]) >= 2

    def test_create_subnet(self):
        """Test creating a subnet."""
        # First create a network
        network_response = client.post(
            "/v2.0/networks",
            json={"network": {"name": "subnet-test-network"}},
        )
        network_id = network_response.json()["network"]["id"]

        # Create subnet
        response = client.post(
            "/v2.0/subnets",
            json={
                "subnet": {
                    "name": "test-subnet",
                    "network_id": network_id,
                    "cidr": "10.0.0.0/24",
                    "ip_version": 4,
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["subnet"]["name"] == "test-subnet"
        assert data["subnet"]["cidr"] == "10.0.0.0/24"

    def test_get_subnet(self):
        """Test getting a specific subnet."""
        # First list to get a subnet ID
        list_response = client.get("/v2.0/subnets")
        subnets = list_response.json()["subnets"]
        subnet_id = subnets[0]["id"]

        response = client.get(f"/v2.0/subnets/{subnet_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["subnet"]["id"] == subnet_id

    def test_update_subnet(self):
        """Test updating a subnet."""
        # Get a subnet
        list_response = client.get("/v2.0/subnets")
        subnets = list_response.json()["subnets"]
        subnet_id = subnets[0]["id"]

        # Update it
        response = client.put(
            f"/v2.0/subnets/{subnet_id}",
            json={"subnet": {"name": "updated-subnet"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subnet"]["name"] == "updated-subnet"


class TestPorts:
    """Test port CRUD operations."""

    def test_list_ports(self):
        """Test listing ports."""
        response = client.get("/v2.0/ports")
        assert response.status_code == 200
        data = response.json()
        assert "ports" in data

    def test_create_port(self):
        """Test creating a port."""
        # Get a network
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        # Find a network with subnets
        network = next((n for n in networks if n.get("subnets")), networks[0])

        response = client.post(
            "/v2.0/ports",
            json={"port": {"name": "test-port", "network_id": network["id"]}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["port"]["name"] == "test-port"
        assert data["port"]["network_id"] == network["id"]
        assert data["port"]["mac_address"]  # Should have a MAC address

    def test_get_port(self):
        """Test getting a specific port."""
        # Create a port first
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        network = next((n for n in networks if n.get("subnets")), networks[0])

        create_response = client.post(
            "/v2.0/ports",
            json={"port": {"name": "get-test-port", "network_id": network["id"]}},
        )
        port_id = create_response.json()["port"]["id"]

        response = client.get(f"/v2.0/ports/{port_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["port"]["id"] == port_id

    def test_update_port(self):
        """Test updating a port."""
        # Create a port first
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        network = next((n for n in networks if n.get("subnets")), networks[0])

        create_response = client.post(
            "/v2.0/ports",
            json={"port": {"name": "update-test-port", "network_id": network["id"]}},
        )
        port_id = create_response.json()["port"]["id"]

        # Update it
        response = client.put(
            f"/v2.0/ports/{port_id}",
            json={"port": {"name": "updated-port"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["port"]["name"] == "updated-port"

    def test_delete_port(self):
        """Test deleting a port."""
        # Create a port first
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        network = next((n for n in networks if n.get("subnets")), networks[0])

        create_response = client.post(
            "/v2.0/ports",
            json={"port": {"name": "delete-test-port", "network_id": network["id"]}},
        )
        port_id = create_response.json()["port"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/ports/{port_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/ports/{port_id}")
        assert get_response.status_code == 404


class TestRouters:
    """Test router CRUD operations."""

    def test_list_routers(self):
        """Test listing routers."""
        response = client.get("/v2.0/routers")
        assert response.status_code == 200
        data = response.json()
        assert "routers" in data

    def test_create_router(self):
        """Test creating a router."""
        response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "test-router"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["router"]["name"] == "test-router"
        assert data["router"]["status"] == "ACTIVE"

    def test_get_router(self):
        """Test getting a specific router."""
        # Create a router first
        create_response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "get-test-router"}},
        )
        router_id = create_response.json()["router"]["id"]

        response = client.get(f"/v2.0/routers/{router_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["router"]["id"] == router_id

    def test_update_router(self):
        """Test updating a router."""
        # Create a router first
        create_response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "update-test-router"}},
        )
        router_id = create_response.json()["router"]["id"]

        # Update it
        response = client.put(
            f"/v2.0/routers/{router_id}",
            json={"router": {"name": "updated-router"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["router"]["name"] == "updated-router"

    def test_delete_router(self):
        """Test deleting a router."""
        # Create a router first
        create_response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "delete-test-router"}},
        )
        router_id = create_response.json()["router"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/routers/{router_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2.0/routers/{router_id}")
        assert get_response.status_code == 404

    def test_add_router_interface(self):
        """Test adding interface to a router."""
        # Create a router
        router_response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "interface-test-router"}},
        )
        router_id = router_response.json()["router"]["id"]

        # Get a subnet
        subnet_response = client.get("/v2.0/subnets")
        subnets = subnet_response.json()["subnets"]
        # Find a non-external subnet
        subnet = next(
            (s for s in subnets if "external" not in s.get("name", "").lower()), subnets[0]
        )

        # Add interface
        response = client.put(
            f"/v2.0/routers/{router_id}/add_router_interface",
            json={"subnet_id": subnet["id"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subnet_id"] == subnet["id"]


class TestFloatingIPs:
    """Test floating IP operations."""

    def test_list_floating_ips(self):
        """Test listing floating IPs."""
        response = client.get("/v2.0/floatingips")
        assert response.status_code == 200
        data = response.json()
        assert "floatingips" in data

    def test_create_floating_ip(self):
        """Test creating a floating IP."""
        # Get external network
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        ext_network = next((n for n in networks if n.get("router:external")), None)
        if not ext_network:
            pytest.skip("No external network available")

        response = client.post(
            "/v2.0/floatingips",
            json={"floatingip": {"floating_network_id": ext_network["id"]}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["floatingip"]["floating_network_id"] == ext_network["id"]
        assert data["floatingip"]["floating_ip_address"]

    def test_get_floating_ip(self):
        """Test getting a specific floating IP."""
        # Get external network
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        ext_network = next((n for n in networks if n.get("router:external")), None)
        if not ext_network:
            pytest.skip("No external network available")

        # Create a floating IP
        create_response = client.post(
            "/v2.0/floatingips",
            json={"floatingip": {"floating_network_id": ext_network["id"]}},
        )
        fip_id = create_response.json()["floatingip"]["id"]

        response = client.get(f"/v2.0/floatingips/{fip_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["floatingip"]["id"] == fip_id

    def test_delete_floating_ip(self):
        """Test deleting a floating IP."""
        # Get external network
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        ext_network = next((n for n in networks if n.get("router:external")), None)
        if not ext_network:
            pytest.skip("No external network available")

        # Create a floating IP
        create_response = client.post(
            "/v2.0/floatingips",
            json={"floatingip": {"floating_network_id": ext_network["id"]}},
        )
        fip_id = create_response.json()["floatingip"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/floatingips/{fip_id}")
        assert response.status_code == 204


class TestSecurityGroups:
    """Test security group operations."""

    def test_list_security_groups(self):
        """Test listing security groups."""
        response = client.get("/v2.0/security-groups")
        assert response.status_code == 200
        data = response.json()
        assert "security_groups" in data
        # Default security group should exist
        assert len(data["security_groups"]) >= 1

    def test_create_security_group(self):
        """Test creating a security group."""
        response = client.post(
            "/v2.0/security-groups",
            json={"security_group": {"name": "test-sg", "description": "Test SG"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["security_group"]["name"] == "test-sg"
        # Should have default egress rules
        assert len(data["security_group"]["security_group_rules"]) >= 2

    def test_get_security_group(self):
        """Test getting a specific security group."""
        # Get the default security group
        list_response = client.get("/v2.0/security-groups")
        sgs = list_response.json()["security_groups"]
        sg_id = sgs[0]["id"]

        response = client.get(f"/v2.0/security-groups/{sg_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["security_group"]["id"] == sg_id

    def test_update_security_group(self):
        """Test updating a security group."""
        # Create a security group
        create_response = client.post(
            "/v2.0/security-groups",
            json={"security_group": {"name": "update-test-sg"}},
        )
        sg_id = create_response.json()["security_group"]["id"]

        # Update it
        response = client.put(
            f"/v2.0/security-groups/{sg_id}",
            json={"security_group": {"name": "updated-sg"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["security_group"]["name"] == "updated-sg"

    def test_delete_security_group(self):
        """Test deleting a security group."""
        # Create a security group
        create_response = client.post(
            "/v2.0/security-groups",
            json={"security_group": {"name": "delete-test-sg"}},
        )
        sg_id = create_response.json()["security_group"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/security-groups/{sg_id}")
        assert response.status_code == 204

    def test_cannot_delete_default_security_group(self):
        """Test that default security group cannot be deleted."""
        # Find the default security group
        list_response = client.get("/v2.0/security-groups")
        sgs = list_response.json()["security_groups"]
        default_sg = next((sg for sg in sgs if sg["name"] == "default"), None)
        if not default_sg:
            pytest.skip("Default security group not found")

        # Try to delete it
        response = client.delete(f"/v2.0/security-groups/{default_sg['id']}")
        assert response.status_code == 409


class TestSecurityGroupRules:
    """Test security group rule operations."""

    def test_list_security_group_rules(self):
        """Test listing security group rules."""
        response = client.get("/v2.0/security-group-rules")
        assert response.status_code == 200
        data = response.json()
        assert "security_group_rules" in data

    def test_create_security_group_rule(self):
        """Test creating a security group rule."""
        # Create a security group first
        sg_response = client.post(
            "/v2.0/security-groups",
            json={"security_group": {"name": "rule-test-sg"}},
        )
        sg_id = sg_response.json()["security_group"]["id"]

        # Create a rule
        response = client.post(
            "/v2.0/security-group-rules",
            json={
                "security_group_rule": {
                    "security_group_id": sg_id,
                    "direction": "ingress",
                    "protocol": "tcp",
                    "port_range_min": 22,
                    "port_range_max": 22,
                    "remote_ip_prefix": "0.0.0.0/0",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["security_group_rule"]["protocol"] == "tcp"
        assert data["security_group_rule"]["port_range_min"] == 22

    def test_delete_security_group_rule(self):
        """Test deleting a security group rule."""
        # Create a security group first
        sg_response = client.post(
            "/v2.0/security-groups",
            json={"security_group": {"name": "rule-delete-test-sg"}},
        )
        sg_id = sg_response.json()["security_group"]["id"]

        # Create a rule
        rule_response = client.post(
            "/v2.0/security-group-rules",
            json={
                "security_group_rule": {
                    "security_group_id": sg_id,
                    "direction": "ingress",
                    "protocol": "tcp",
                    "port_range_min": 80,
                    "port_range_max": 80,
                }
            },
        )
        rule_id = rule_response.json()["security_group_rule"]["id"]

        # Delete it
        response = client.delete(f"/v2.0/security-group-rules/{rule_id}")
        assert response.status_code == 204


class TestExtensions:
    """Test extensions endpoint."""

    def test_list_extensions(self):
        """Test listing extensions."""
        response = client.get("/v2.0/extensions")
        assert response.status_code == 200
        data = response.json()
        assert "extensions" in data
        # Should have at least router and security-group extensions
        aliases = [ext["alias"] for ext in data["extensions"]]
        assert "router" in aliases
        assert "security-group" in aliases


class TestDefaultResources:
    """Test that default resources are created."""

    def test_default_networks_exist(self):
        """Test that default networks are created."""
        response = client.get("/v2.0/networks")
        networks = response.json()["networks"]
        names = [n["name"] for n in networks]
        assert "external" in names
        assert "private" in names

    def test_external_network_is_external(self):
        """Test that external network has router:external set."""
        response = client.get("/v2.0/networks")
        networks = response.json()["networks"]
        ext_network = next((n for n in networks if n["name"] == "external"), None)
        assert ext_network is not None
        assert ext_network["router:external"] is True

    def test_default_security_group_exists(self):
        """Test that default security group is created."""
        response = client.get("/v2.0/security-groups")
        sgs = response.json()["security_groups"]
        names = [sg["name"] for sg in sgs]
        assert "default" in names
