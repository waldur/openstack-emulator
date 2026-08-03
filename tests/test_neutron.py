"""Tests for Neutron Networking API emulator."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import scoped_token


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    db.reset_neutron()
    yield


# Create the app once at module level
_apps = create_all_service_apps()
client = TestClient(_apps["neutron"])


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

    def test_list_ports_fixed_ips_subnet_filter(self):
        """Ports can be filtered by the Neutron fixed_ips=subnet_id= query.

        This is what get_free_ip relies on to find used IPs on a subnet.
        """
        net = client.post("/v2.0/networks", json={"network": {"name": "fip-filter-net"}}).json()[
            "network"
        ]
        sub = client.post(
            "/v2.0/subnets",
            json={
                "subnet": {
                    "network_id": net["id"],
                    "ip_version": 4,
                    "cidr": "10.5.0.0/24",
                }
            },
        ).json()["subnet"]
        port = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "name": "fip-filter-port",
                    "network_id": net["id"],
                    "fixed_ips": [{"subnet_id": sub["id"], "ip_address": "10.5.0.10"}],
                }
            },
        ).json()["port"]

        matching = client.get("/v2.0/ports", params={"fixed_ips": f"subnet_id={sub['id']}"})
        assert matching.status_code == 200
        assert port["id"] in [p["id"] for p in matching.json()["ports"]]

        other = client.get("/v2.0/ports", params={"fixed_ips": "subnet_id=does-not-exist"})
        assert port["id"] not in [p["id"] for p in other.json()["ports"]]

    def _make_net_with_subnet(self, name, cidr):
        net = client.post("/v2.0/networks", json={"network": {"name": name}}).json()["network"]
        sub = client.post(
            "/v2.0/subnets",
            json={"subnet": {"network_id": net["id"], "ip_version": 4, "cidr": cidr}},
        ).json()["subnet"]
        return net, sub

    def test_create_port_out_of_cidr_ip_returns_400(self):
        """Real Neutron rejects an IP outside every subnet CIDR (InvalidIpForNetwork)."""
        net, sub = self._make_net_with_subnet("bad-ip-net", "10.6.0.0/24")
        response = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": net["id"],
                    "fixed_ips": [{"subnet_id": sub["id"], "ip_address": "10.99.0.1"}],
                }
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["message"] == (
            "IP address 10.99.0.1 is not a valid IP for any of "
            "the subnets on the specified network."
        )

    def test_create_port_duplicate_ip_returns_409(self):
        """Real Neutron rejects an already-allocated IP (IpAddressAlreadyAllocated)."""
        net, sub = self._make_net_with_subnet("dup-ip-net", "10.7.0.0/24")
        payload = {
            "port": {
                "network_id": net["id"],
                "fixed_ips": [{"subnet_id": sub["id"], "ip_address": "10.7.0.5"}],
            }
        }
        first = client.post("/v2.0/ports", json=payload)
        assert first.status_code == 201

        second = client.post("/v2.0/ports", json=payload)
        assert second.status_code == 409
        assert "10.7.0.5 already allocated" in second.json()["error"]["message"]

    def test_create_port_resolves_subnet_id_from_cidr(self):
        """An explicit IP without subnet_id gets the containing subnet's id."""
        net, sub = self._make_net_with_subnet("resolve-subnet-net", "10.8.0.0/24")
        response = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": net["id"],
                    "fixed_ips": [{"ip_address": "10.8.0.5"}],
                }
            },
        )
        assert response.status_code == 201
        assert response.json()["port"]["fixed_ips"][0]["subnet_id"] == sub["id"]


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

    def _external_network_id(self):
        """Return the id of the seeded external network."""
        networks = client.get("/v2.0/networks?router:external=true").json()["networks"]
        return networks[0]["id"]

    def test_set_gateway_allocates_external_fixed_ip(self):
        """A gateway set without fixed IPs gets one from the external subnet.

        Real Neutron allocates the address and reports it back; clients such as
        Waldur read external_fixed_ips[0] straight after the call.
        """
        net_id = self._external_network_id()

        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "gateway-router",
                    "external_gateway_info": {"network_id": net_id},
                }
            },
        )
        assert response.status_code == 201, response.text
        router = response.json()["router"]
        fixed_ips = router["external_gateway_info"]["external_fixed_ips"]
        assert len(fixed_ips) == 1
        assert fixed_ips[0]["ip_address"].startswith("203.0.113.")
        assert fixed_ips[0]["subnet_id"]

        # The allocation is backed by a gateway port, as in real Neutron.
        ports = client.get(f"/v2.0/ports?network_id={net_id}").json()["ports"]
        gateway_ports = [p for p in ports if p["device_owner"] == "network:router_gateway"]
        assert len(gateway_ports) == 1
        assert gateway_ports[0]["device_id"] == router["id"]

    def test_clearing_gateway_releases_the_port(self):
        """Removing the gateway drops its port so the pool does not leak."""
        net_id = self._external_network_id()

        router_id = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "gateway-release-router",
                    "external_gateway_info": {"network_id": net_id},
                }
            },
        ).json()["router"]["id"]

        response = client.put(
            f"/v2.0/routers/{router_id}",
            json={"router": {"external_gateway_info": {}}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["router"]["external_gateway_info"] is None

        ports = client.get(f"/v2.0/ports?network_id={net_id}").json()["ports"]
        assert [p for p in ports if p["device_owner"] == "network:router_gateway"] == []

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

    def test_create_floating_ip_creates_port(self):
        """Test that creating a floating IP also creates a port on the external network.

        In real OpenStack Neutron, when a floating IP is created, a port is created
        on the external network with device_owner='network:floatingip' to hold the
        floating IP address.
        """
        # Get external network
        network_response = client.get("/v2.0/networks")
        networks = network_response.json()["networks"]
        ext_network = next((n for n in networks if n.get("router:external")), None)
        if not ext_network:
            pytest.skip("No external network available")

        # Get initial port count on external network
        initial_ports = client.get(f"/v2.0/ports?network_id={ext_network['id']}").json()["ports"]
        initial_port_count = len(initial_ports)

        # Create a floating IP
        response = client.post(
            "/v2.0/floatingips",
            json={"floatingip": {"floating_network_id": ext_network["id"]}},
        )
        assert response.status_code == 201
        fip_data = response.json()["floatingip"]

        # Verify floating_port_id is set
        assert fip_data.get("floating_port_id") is not None
        floating_port_id = fip_data["floating_port_id"]

        # Verify the port was created on the external network
        port_response = client.get(f"/v2.0/ports/{floating_port_id}")
        assert port_response.status_code == 200
        port_data = port_response.json()["port"]

        # Verify port properties
        assert port_data["network_id"] == ext_network["id"]
        assert port_data["device_owner"] == "network:floatingip"
        assert port_data["device_id"] == fip_data["id"]

        # Verify the port has the floating IP address
        assert len(port_data["fixed_ips"]) > 0
        assert port_data["fixed_ips"][0]["ip_address"] == fip_data["floating_ip_address"]

        # Verify port count increased
        final_ports = client.get(f"/v2.0/ports?network_id={ext_network['id']}").json()["ports"]
        assert len(final_ports) == initial_port_count + 1

    def test_delete_floating_ip_deletes_port(self):
        """Test that deleting a floating IP also deletes its associated port.

        When a floating IP is deleted, the port on the external network that
        was created to hold the floating IP address should also be deleted.
        """
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
        fip_data = create_response.json()["floatingip"]
        fip_id = fip_data["id"]
        floating_port_id = fip_data["floating_port_id"]

        # Verify the port exists
        port_response = client.get(f"/v2.0/ports/{floating_port_id}")
        assert port_response.status_code == 200

        # Delete the floating IP
        delete_response = client.delete(f"/v2.0/floatingips/{fip_id}")
        assert delete_response.status_code == 204

        # Verify the associated port was also deleted
        port_response = client.get(f"/v2.0/ports/{floating_port_id}")
        assert port_response.status_code == 404

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


class TestRbacExternalNetworks:
    """Cross-tenant RBAC sharing and external-gateway scenarios.

    Covers a tenant sharing its own network to another tenant as external,
    target-tenant visibility, isolation from third tenants, and the
    router external-gateway validation that depends on it.
    """

    @staticmethod
    def _token_for(project: str) -> str:
        """Create a project and return an auth token scoped to it."""
        return scoped_token(project_name=project, project_id=project).id

    @staticmethod
    def _create_network(token: str, name: str, **attrs) -> str:
        response = client.post(
            "/v2.0/networks",
            json={"network": {"name": name, **attrs}},
            headers={"X-Auth-Token": token},
        )
        assert response.status_code == 201, response.text
        return response.json()["network"]["id"]

    @staticmethod
    def _share(token: str, network_id: str, target: str, action: str) -> None:
        response = client.post(
            "/v2.0/rbac-policies",
            json={
                "rbac_policy": {
                    "object_type": "network",
                    "object_id": network_id,
                    "target_tenant": target,
                    "action": action,
                }
            },
            headers={"X-Auth-Token": token},
        )
        assert response.status_code == 201, response.text

    def test_access_as_external_grants_target_visibility(self):
        """Tenant B sees A's network shared as external; tenant C does not."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")
        token_c = self._token_for("tenant-c")

        net_id = self._create_network(token_a, "shared-ext")
        self._share(token_a, net_id, "tenant-b", "access_as_external")

        b_networks = client.get("/v2.0/networks", headers={"X-Auth-Token": token_b}).json()[
            "networks"
        ]
        assert net_id in [n["id"] for n in b_networks]

        c_networks = client.get("/v2.0/networks", headers={"X-Auth-Token": token_c}).json()[
            "networks"
        ]
        assert net_id not in [n["id"] for n in c_networks]

    def test_access_as_external_appears_in_external_filter(self):
        """The shared network is returned when target tenant filters external."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")

        net_id = self._create_network(token_a, "shared-ext")
        self._share(token_a, net_id, "tenant-b", "access_as_external")

        ext_for_b = client.get(
            "/v2.0/networks?router:external=true",
            headers={"X-Auth-Token": token_b},
        ).json()["networks"]
        assert net_id in [n["id"] for n in ext_for_b]

    def test_access_as_shared_is_not_external(self):
        """access_as_shared grants visibility but not external-gateway eligibility."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")

        net_id = self._create_network(token_a, "shared-only")
        self._share(token_a, net_id, "tenant-b", "access_as_shared")

        # Visible to B
        b_networks = client.get("/v2.0/networks", headers={"X-Auth-Token": token_b}).json()[
            "networks"
        ]
        assert net_id in [n["id"] for n in b_networks]

        # But not as external
        ext_for_b = client.get(
            "/v2.0/networks?router:external=true",
            headers={"X-Auth-Token": token_b},
        ).json()["networks"]
        assert net_id not in [n["id"] for n in ext_for_b]

    def test_wildcard_external_visible_to_all(self):
        """Regression: access_as_external to '*' is external for every tenant."""
        token_a = self._token_for("tenant-a")
        token_c = self._token_for("tenant-c")

        net_id = self._create_network(token_a, "wild-ext")
        self._share(token_a, net_id, "*", "access_as_external")

        ext_for_c = client.get(
            "/v2.0/networks?router:external=true",
            headers={"X-Auth-Token": token_c},
        ).json()["networks"]
        assert net_id in [n["id"] for n in ext_for_c]

    def test_set_gateway_to_shared_external_with_snat_and_fixed_ip(self):
        """Tenant B sets A's RBAC-external network as gateway with SNAT off + fixed IP."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")

        net_id = self._create_network(token_a, "shared-ext")
        self._share(token_a, net_id, "tenant-b", "access_as_external")

        gateway = {
            "network_id": net_id,
            "enable_snat": False,
            "external_fixed_ips": [{"ip_address": "10.10.10.1"}],
        }
        response = client.post(
            "/v2.0/routers",
            json={"router": {"name": "b-router", "external_gateway_info": gateway}},
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 201, response.text
        info = response.json()["router"]["external_gateway_info"]
        assert info["network_id"] == net_id
        assert info["enable_snat"] is False
        assert info["external_fixed_ips"] == [{"subnet_id": "", "ip_address": "10.10.10.1"}]

    def test_set_gateway_rejected_for_non_target_tenant(self):
        """Tenant C cannot use A's network (shared only to B) as a gateway."""
        token_a = self._token_for("tenant-a")
        token_c = self._token_for("tenant-c")

        net_id = self._create_network(token_a, "shared-ext")
        self._share(token_a, net_id, "tenant-b", "access_as_external")

        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "c-router",
                    "external_gateway_info": {"network_id": net_id},
                }
            },
            headers={"X-Auth-Token": token_c},
        )
        # Not visible to C at all -> treated as not found.
        assert response.status_code == 404, response.text

    def test_set_gateway_rejected_for_non_external_network(self):
        """A network shared only as access_as_shared cannot be a gateway."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")

        net_id = self._create_network(token_a, "shared-only")
        self._share(token_a, net_id, "tenant-b", "access_as_shared")

        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "b-router",
                    "external_gateway_info": {"network_id": net_id},
                }
            },
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 400, response.text

    def test_set_gateway_to_missing_network(self):
        """Setting a gateway to a non-existent network is rejected."""
        token_b = self._token_for("tenant-b")
        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "b-router",
                    "external_gateway_info": {"network_id": "does-not-exist"},
                }
            },
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 404, response.text

    def test_update_router_gateway_validates(self):
        """Updating a router gateway is validated the same way as create."""
        token_b = self._token_for("tenant-b")
        create = client.post(
            "/v2.0/routers",
            json={"router": {"name": "b-router"}},
            headers={"X-Auth-Token": token_b},
        )
        router_id = create.json()["router"]["id"]

        response = client.put(
            f"/v2.0/routers/{router_id}",
            json={"router": {"external_gateway_info": {"network_id": "does-not-exist"}}},
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 404, response.text

    def test_rbac_accepts_target_project_id_alias(self):
        """RBAC create accepts the newer target_project_id field alias."""
        token_a = self._token_for("tenant-a")
        token_b = self._token_for("tenant-b")
        net_id = self._create_network(token_a, "shared-ext")

        response = client.post(
            "/v2.0/rbac-policies",
            json={
                "rbac_policy": {
                    "object_type": "network",
                    "object_id": net_id,
                    "target_project_id": "tenant-b",
                    "action": "access_as_external",
                }
            },
            headers={"X-Auth-Token": token_a},
        )
        assert response.status_code == 201, response.text

        ext_for_b = client.get(
            "/v2.0/networks?router:external=true",
            headers={"X-Auth-Token": token_b},
        ).json()["networks"]
        assert net_id in [n["id"] for n in ext_for_b]

    def test_set_gateway_requires_network_id(self):
        """external_gateway_info without network_id is rejected (Neutron requires it)."""
        token_b = self._token_for("tenant-b")
        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "b-router",
                    "external_gateway_info": {"enable_snat": False},
                }
            },
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 400, response.text

    def test_default_external_network_usable_by_any_tenant(self):
        """Regression: the globally-external default network still works as a gateway."""
        token_b = self._token_for("tenant-b")
        networks = client.get(
            "/v2.0/networks?router:external=true",
            headers={"X-Auth-Token": token_b},
        ).json()["networks"]
        ext = next(n for n in networks if n["name"] == "external")

        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "b-router",
                    "external_gateway_info": {"network_id": ext["id"]},
                }
            },
            headers={"X-Auth-Token": token_b},
        )
        assert response.status_code == 201, response.text
