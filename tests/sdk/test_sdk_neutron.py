"""SDK tests for Neutron Network service."""

from openstack.connection import Connection


class TestNeutronNetworks:
    """Test Neutron network operations via SDK."""

    def test_list_networks(self, openstack_connection: Connection) -> None:
        """Test listing networks."""
        networks = list(openstack_connection.network.networks())
        assert len(networks) > 0

        # Default network should exist
        network_names = [n.name for n in networks]
        assert "private" in network_names

    def test_get_network(self, openstack_connection: Connection) -> None:
        """Test getting a specific network."""
        networks = list(openstack_connection.network.networks())
        assert len(networks) > 0

        network = openstack_connection.network.get_network(networks[0].id)
        assert network is not None
        assert network.id == networks[0].id

    def test_find_network_by_name(self, openstack_connection: Connection) -> None:
        """Test finding a network by name."""
        network = openstack_connection.network.find_network("private")
        assert network is not None
        assert network.name == "private"

    def test_create_network(self, openstack_connection: Connection) -> None:
        """Test creating a network."""
        network = openstack_connection.network.create_network(
            name="test-sdk-network",
            description="Test network created via SDK",
        )
        assert network is not None
        assert network.name == "test-sdk-network"
        assert network.description == "Test network created via SDK"

    def test_update_network(self, openstack_connection: Connection) -> None:
        """Test updating a network."""
        # Create a network first
        network = openstack_connection.network.create_network(
            name="test-update-network",
        )

        # Update it
        updated = openstack_connection.network.update_network(
            network.id,
            description="Updated description",
        )
        assert updated.description == "Updated description"

    def test_delete_network(self, openstack_connection: Connection) -> None:
        """Test deleting a network."""
        # Create a network first
        network = openstack_connection.network.create_network(
            name="test-delete-network",
        )

        # Delete it
        result = openstack_connection.network.delete_network(network.id)
        assert result is None  # delete returns None on success


class TestNeutronSubnets:
    """Test Neutron subnet operations via SDK."""

    def test_list_subnets(self, openstack_connection: Connection) -> None:
        """Test listing subnets."""
        # Create a network and subnet first since default ones might not be visible
        network = openstack_connection.network.create_network(
            name="test-list-subnets-network",
        )
        openstack_connection.network.create_subnet(
            name="test-list-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.100.0.0/24",
        )
        subnets = list(openstack_connection.network.subnets())
        assert len(subnets) > 0

    def test_get_subnet(self, openstack_connection: Connection) -> None:
        """Test getting a specific subnet."""
        # Create a network and subnet first
        network = openstack_connection.network.create_network(
            name="test-get-subnet-network",
        )
        subnet = openstack_connection.network.create_subnet(
            name="test-get-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.101.0.0/24",
        )

        fetched = openstack_connection.network.get_subnet(subnet.id)
        assert fetched is not None
        assert fetched.id == subnet.id

    def test_create_subnet(self, openstack_connection: Connection) -> None:
        """Test creating a subnet."""
        # Create a network first
        network = openstack_connection.network.create_network(
            name="test-subnet-network",
        )

        # Create a subnet
        subnet = openstack_connection.network.create_subnet(
            name="test-sdk-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.99.0.0/24",
        )
        assert subnet is not None
        assert subnet.name == "test-sdk-subnet"
        assert subnet.cidr == "10.99.0.0/24"

    def test_update_subnet(self, openstack_connection: Connection) -> None:
        """Test updating a subnet."""
        # Create network and subnet first
        network = openstack_connection.network.create_network(
            name="test-update-subnet-network",
        )
        subnet = openstack_connection.network.create_subnet(
            name="test-update-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.98.0.0/24",
        )

        # Update it
        updated = openstack_connection.network.update_subnet(
            subnet.id,
            name="test-update-subnet-renamed",
        )
        assert updated.name == "test-update-subnet-renamed"

    def test_delete_subnet(self, openstack_connection: Connection) -> None:
        """Test deleting a subnet."""
        # Create network and subnet first
        network = openstack_connection.network.create_network(
            name="test-delete-subnet-network",
        )
        subnet = openstack_connection.network.create_subnet(
            name="test-delete-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.97.0.0/24",
        )

        # Delete it
        result = openstack_connection.network.delete_subnet(subnet.id)
        assert result is None  # delete returns None on success


class TestNeutronPorts:
    """Test Neutron port operations via SDK."""

    def test_list_ports(self, openstack_connection: Connection) -> None:
        """Test listing ports."""
        ports = list(openstack_connection.network.ports())
        # May be empty initially
        assert isinstance(ports, list)

    def test_create_port(self, openstack_connection: Connection) -> None:
        """Test creating a port."""
        # Get a network
        network = openstack_connection.network.find_network("private")
        assert network is not None

        # Create a port
        port = openstack_connection.network.create_port(
            name="test-sdk-port",
            network_id=network.id,
        )
        assert port is not None
        assert port.name == "test-sdk-port"
        assert port.network_id == network.id

    def test_get_port(self, openstack_connection: Connection) -> None:
        """Test getting a specific port."""
        # Create a port first
        network = openstack_connection.network.find_network("private")
        port = openstack_connection.network.create_port(
            name="test-get-port",
            network_id=network.id,
        )

        # Get it
        fetched = openstack_connection.network.get_port(port.id)
        assert fetched is not None
        assert fetched.id == port.id

    def test_update_port(self, openstack_connection: Connection) -> None:
        """Test updating a port."""
        # Create a port first
        network = openstack_connection.network.find_network("private")
        port = openstack_connection.network.create_port(
            name="test-update-port",
            network_id=network.id,
        )

        # Update it
        updated = openstack_connection.network.update_port(
            port.id,
            name="test-update-port-renamed",
        )
        assert updated.name == "test-update-port-renamed"

    def test_delete_port(self, openstack_connection: Connection) -> None:
        """Test deleting a port."""
        # Create a port first
        network = openstack_connection.network.find_network("private")
        port = openstack_connection.network.create_port(
            name="test-delete-port",
            network_id=network.id,
        )

        # Delete it
        result = openstack_connection.network.delete_port(port.id)
        assert result is None  # delete returns None on success


class TestNeutronRouters:
    """Test Neutron router operations via SDK."""

    def test_list_routers(self, openstack_connection: Connection) -> None:
        """Test listing routers."""
        routers = list(openstack_connection.network.routers())
        # May be empty initially
        assert isinstance(routers, list)

    def test_create_router(self, openstack_connection: Connection) -> None:
        """Test creating a router."""
        router = openstack_connection.network.create_router(
            name="test-sdk-router",
            description="Test router created via SDK",
        )
        assert router is not None
        assert router.name == "test-sdk-router"

    def test_get_router(self, openstack_connection: Connection) -> None:
        """Test getting a specific router."""
        # Create a router first
        router = openstack_connection.network.create_router(
            name="test-get-router",
        )

        # Get it
        fetched = openstack_connection.network.get_router(router.id)
        assert fetched is not None
        assert fetched.id == router.id

    def test_update_router(self, openstack_connection: Connection) -> None:
        """Test updating a router."""
        # Create a router first
        router = openstack_connection.network.create_router(
            name="test-update-router",
        )

        # Update it
        updated = openstack_connection.network.update_router(
            router.id,
            description="Updated router description",
        )
        assert updated.description == "Updated router description"

    def test_delete_router(self, openstack_connection: Connection) -> None:
        """Test deleting a router."""
        # Create a router first
        router = openstack_connection.network.create_router(
            name="test-delete-router",
        )

        # Delete it
        result = openstack_connection.network.delete_router(router.id)
        assert result is None  # delete returns None on success

    def test_add_router_interface(self, openstack_connection: Connection) -> None:
        """Test adding an interface to a router."""
        # Create network and subnet
        network = openstack_connection.network.create_network(
            name="test-router-interface-network",
        )
        subnet = openstack_connection.network.create_subnet(
            name="test-router-interface-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.96.0.0/24",
        )

        # Create router
        router = openstack_connection.network.create_router(
            name="test-router-interface",
        )

        # Add interface
        result = openstack_connection.network.add_interface_to_router(
            router.id,
            subnet_id=subnet.id,
        )
        assert result is not None

    def test_remove_router_interface(self, openstack_connection: Connection) -> None:
        """Test removing an interface from a router."""
        # Create network and subnet
        network = openstack_connection.network.create_network(
            name="test-remove-router-interface-network",
        )
        subnet = openstack_connection.network.create_subnet(
            name="test-remove-router-interface-subnet",
            network_id=network.id,
            ip_version=4,
            cidr="10.95.0.0/24",
        )

        # Create router and add interface
        router = openstack_connection.network.create_router(
            name="test-remove-router-interface",
        )
        openstack_connection.network.add_interface_to_router(
            router.id,
            subnet_id=subnet.id,
        )

        # Remove interface
        result = openstack_connection.network.remove_interface_from_router(
            router.id,
            subnet_id=subnet.id,
        )
        assert result is not None


class TestNeutronSecurityGroups:
    """Test Neutron security group operations via SDK."""

    def test_list_security_groups(self, openstack_connection: Connection) -> None:
        """Test listing security groups."""
        # Create a security group first since default might not be visible
        openstack_connection.network.create_security_group(
            name="test-list-sg",
        )
        groups = list(openstack_connection.network.security_groups())
        assert len(groups) > 0

    def test_get_security_group(self, openstack_connection: Connection) -> None:
        """Test getting a specific security group."""
        # Create a security group first
        group = openstack_connection.network.create_security_group(
            name="test-get-sg",
        )

        fetched = openstack_connection.network.get_security_group(group.id)
        assert fetched is not None
        assert fetched.id == group.id

    def test_find_security_group_by_name(self, openstack_connection: Connection) -> None:
        """Test finding a security group by name."""
        # Create a security group first
        openstack_connection.network.create_security_group(
            name="test-find-sg",
        )

        group = openstack_connection.network.find_security_group("test-find-sg")
        assert group is not None
        assert group.name == "test-find-sg"

    def test_create_security_group(self, openstack_connection: Connection) -> None:
        """Test creating a security group."""
        group = openstack_connection.network.create_security_group(
            name="test-sdk-security-group",
            description="Test security group created via SDK",
        )
        assert group is not None
        assert group.name == "test-sdk-security-group"

    def test_delete_security_group(self, openstack_connection: Connection) -> None:
        """Test deleting a security group."""
        # Create a security group first
        group = openstack_connection.network.create_security_group(
            name="test-delete-security-group",
        )

        # Delete it
        result = openstack_connection.network.delete_security_group(group.id)
        assert result is None  # delete returns None on success


class TestNeutronSecurityGroupRules:
    """Test Neutron security group rule operations via SDK."""

    def test_list_security_group_rules(self, openstack_connection: Connection) -> None:
        """Test listing security group rules."""
        # Create a security group with rules first
        group = openstack_connection.network.create_security_group(
            name="test-list-rules-sg",
        )
        # Create a rule
        openstack_connection.network.create_security_group_rule(
            security_group_id=group.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=443,
            port_range_max=443,
        )
        rules = list(openstack_connection.network.security_group_rules())
        assert len(rules) > 0

    def test_create_security_group_rule(self, openstack_connection: Connection) -> None:
        """Test creating a security group rule."""
        # Create a security group first
        group = openstack_connection.network.create_security_group(
            name="test-rule-security-group",
        )

        # Create a rule (allow SSH ingress)
        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=group.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=22,
            port_range_max=22,
            remote_ip_prefix="0.0.0.0/0",
        )
        assert rule is not None
        assert rule.direction == "ingress"
        assert rule.protocol == "tcp"
        assert rule.port_range_min == 22
        assert rule.port_range_max == 22

    def test_delete_security_group_rule(self, openstack_connection: Connection) -> None:
        """Test deleting a security group rule."""
        # Create security group and rule
        group = openstack_connection.network.create_security_group(
            name="test-delete-rule-security-group",
        )
        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=group.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=80,
            port_range_max=80,
        )

        # Delete the rule
        result = openstack_connection.network.delete_security_group_rule(rule.id)
        assert result is None  # delete returns None on success


class TestNeutronFloatingIPs:
    """Test Neutron floating IP operations via SDK."""

    def test_list_floating_ips(self, openstack_connection: Connection) -> None:
        """Test listing floating IPs."""
        fips = list(openstack_connection.network.ips())
        # May be empty initially
        assert isinstance(fips, list)

    def test_create_floating_ip(self, openstack_connection: Connection) -> None:
        """Test creating a floating IP."""
        # Find the external network
        external_network = openstack_connection.network.find_network("external")
        assert external_network is not None

        # Create a floating IP
        fip = openstack_connection.network.create_ip(
            floating_network_id=external_network.id,
        )
        assert fip is not None
        assert fip.floating_network_id == external_network.id

    def test_get_floating_ip(self, openstack_connection: Connection) -> None:
        """Test getting a specific floating IP."""
        # Create a floating IP first
        external_network = openstack_connection.network.find_network("external")
        fip = openstack_connection.network.create_ip(
            floating_network_id=external_network.id,
        )

        # Get it
        fetched = openstack_connection.network.get_ip(fip.id)
        assert fetched is not None
        assert fetched.id == fip.id

    def test_delete_floating_ip(self, openstack_connection: Connection) -> None:
        """Test deleting a floating IP."""
        # Create a floating IP first
        external_network = openstack_connection.network.find_network("external")
        fip = openstack_connection.network.create_ip(
            floating_network_id=external_network.id,
        )

        # Delete it
        result = openstack_connection.network.delete_ip(fip.id)
        assert result is None  # delete returns None on success
