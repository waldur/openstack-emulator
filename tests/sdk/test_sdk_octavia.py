"""SDK tests for Octavia Load Balancer service."""

from openstack.connection import Connection


def _create_network_and_subnet(openstack_connection: Connection, name_suffix: str) -> tuple:
    """Helper to create a network and subnet for testing."""
    # Create network
    network = openstack_connection.network.create_network(
        name=f"test-lb-network-{name_suffix}",
    )
    # Create subnet
    subnet = openstack_connection.network.create_subnet(
        name=f"test-lb-subnet-{name_suffix}",
        network_id=network.id,
        ip_version=4,
        cidr=f"10.{hash(name_suffix) % 256}.0.0/24",
    )
    return network, subnet


class TestOctaviaLoadBalancers:
    """Test Octavia load balancer operations via SDK."""

    def test_list_load_balancers(self, openstack_connection: Connection) -> None:
        """Test listing load balancers."""
        lbs = list(openstack_connection.load_balancer.load_balancers())
        # May be empty initially
        assert isinstance(lbs, list)

    def test_create_load_balancer(self, openstack_connection: Connection) -> None:
        """Test creating a load balancer."""
        # Create a network and subnet for the VIP
        network, subnet = _create_network_and_subnet(openstack_connection, "create-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-sdk-lb",
            description="Test LB created via SDK",
            vip_subnet_id=subnet.id,
        )
        assert lb is not None
        assert lb.name == "test-sdk-lb"
        assert lb.description == "Test LB created via SDK"
        assert lb.vip_subnet_id == subnet.id

    def test_get_load_balancer(self, openstack_connection: Connection) -> None:
        """Test getting a specific load balancer."""
        # Create network, subnet, and load balancer
        network, subnet = _create_network_and_subnet(openstack_connection, "get-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-get-lb",
            vip_subnet_id=subnet.id,
        )

        # Get it
        fetched = openstack_connection.load_balancer.get_load_balancer(lb.id)
        assert fetched is not None
        assert fetched.id == lb.id
        assert fetched.name == "test-get-lb"

    def test_find_load_balancer_by_name(self, openstack_connection: Connection) -> None:
        """Test finding a load balancer by name."""
        # Create network, subnet, and load balancer
        network, subnet = _create_network_and_subnet(openstack_connection, "find-lb")

        openstack_connection.load_balancer.create_load_balancer(
            name="test-find-lb",
            vip_subnet_id=subnet.id,
        )

        # Find it by name
        lb = openstack_connection.load_balancer.find_load_balancer("test-find-lb")
        assert lb is not None
        assert lb.name == "test-find-lb"

    def test_update_load_balancer(self, openstack_connection: Connection) -> None:
        """Test updating a load balancer."""
        # Create network, subnet, and load balancer
        network, subnet = _create_network_and_subnet(openstack_connection, "update-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-update-lb",
            vip_subnet_id=subnet.id,
        )

        # Update it
        updated = openstack_connection.load_balancer.update_load_balancer(
            lb.id,
            description="Updated description",
        )
        assert updated.description == "Updated description"

    def test_delete_load_balancer(self, openstack_connection: Connection) -> None:
        """Test deleting a load balancer."""
        # Create network, subnet, and load balancer
        network, subnet = _create_network_and_subnet(openstack_connection, "delete-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-delete-lb",
            vip_subnet_id=subnet.id,
        )

        # Delete it
        openstack_connection.load_balancer.delete_load_balancer(lb.id)
        # Verify deletion
        deleted = openstack_connection.load_balancer.find_load_balancer(lb.id)
        assert deleted is None


class TestOctaviaListeners:
    """Test Octavia listener operations via SDK."""

    def _create_load_balancer(self, openstack_connection: Connection) -> object:
        """Helper to create a load balancer for listener tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "listener-lb")

        return openstack_connection.load_balancer.create_load_balancer(
            name="test-listener-lb",
            vip_subnet_id=subnet.id,
        )

    def test_list_listeners(self, openstack_connection: Connection) -> None:
        """Test listing listeners."""
        listeners = list(openstack_connection.load_balancer.listeners())
        # May be empty initially
        assert isinstance(listeners, list)

    def test_create_listener(self, openstack_connection: Connection) -> None:
        """Test creating a listener."""
        lb = self._create_load_balancer(openstack_connection)

        listener = openstack_connection.load_balancer.create_listener(
            name="test-sdk-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )
        assert listener is not None
        assert listener.name == "test-sdk-listener"
        assert listener.protocol == "HTTP"
        assert listener.protocol_port == 80

    def test_get_listener(self, openstack_connection: Connection) -> None:
        """Test getting a specific listener."""
        lb = self._create_load_balancer(openstack_connection)
        listener = openstack_connection.load_balancer.create_listener(
            name="test-get-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=8080,
        )

        fetched = openstack_connection.load_balancer.get_listener(listener.id)
        assert fetched is not None
        assert fetched.id == listener.id

    def test_update_listener(self, openstack_connection: Connection) -> None:
        """Test updating a listener."""
        lb = self._create_load_balancer(openstack_connection)
        listener = openstack_connection.load_balancer.create_listener(
            name="test-update-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=8081,
        )

        updated = openstack_connection.load_balancer.update_listener(
            listener.id,
            description="Updated listener",
        )
        assert updated.description == "Updated listener"

    def test_delete_listener(self, openstack_connection: Connection) -> None:
        """Test deleting a listener."""
        lb = self._create_load_balancer(openstack_connection)
        listener = openstack_connection.load_balancer.create_listener(
            name="test-delete-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=8082,
        )

        result = openstack_connection.load_balancer.delete_listener(listener.id)
        assert result is None


class TestOctaviaPools:
    """Test Octavia pool operations via SDK."""

    def _create_load_balancer_with_listener(self, openstack_connection: Connection) -> tuple:
        """Helper to create a load balancer and listener for pool tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "pool-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-pool-lb",
            vip_subnet_id=subnet.id,
        )

        listener = openstack_connection.load_balancer.create_listener(
            name="test-pool-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )

        return lb, listener

    def test_list_pools(self, openstack_connection: Connection) -> None:
        """Test listing pools."""
        pools = list(openstack_connection.load_balancer.pools())
        # May be empty initially
        assert isinstance(pools, list)

    def test_create_pool(self, openstack_connection: Connection) -> None:
        """Test creating a pool."""
        lb, listener = self._create_load_balancer_with_listener(openstack_connection)

        pool = openstack_connection.load_balancer.create_pool(
            name="test-sdk-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )
        assert pool is not None
        assert pool.name == "test-sdk-pool"
        assert pool.protocol == "HTTP"
        assert pool.lb_algorithm == "ROUND_ROBIN"

    def test_get_pool(self, openstack_connection: Connection) -> None:
        """Test getting a specific pool."""
        lb, listener = self._create_load_balancer_with_listener(openstack_connection)
        pool = openstack_connection.load_balancer.create_pool(
            name="test-get-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )

        fetched = openstack_connection.load_balancer.get_pool(pool.id)
        assert fetched is not None
        assert fetched.id == pool.id

    def test_update_pool(self, openstack_connection: Connection) -> None:
        """Test updating a pool."""
        lb, listener = self._create_load_balancer_with_listener(openstack_connection)
        pool = openstack_connection.load_balancer.create_pool(
            name="test-update-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )

        updated = openstack_connection.load_balancer.update_pool(
            pool.id,
            description="Updated pool",
        )
        assert updated.description == "Updated pool"

    def test_delete_pool(self, openstack_connection: Connection) -> None:
        """Test deleting a pool."""
        lb, listener = self._create_load_balancer_with_listener(openstack_connection)
        pool = openstack_connection.load_balancer.create_pool(
            name="test-delete-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )

        openstack_connection.load_balancer.delete_pool(pool.id)
        # Verify deletion
        deleted = openstack_connection.load_balancer.find_pool(pool.id)
        assert deleted is None


class TestOctaviaMembers:
    """Test Octavia pool member operations via SDK."""

    def _create_pool(self, openstack_connection: Connection) -> tuple:
        """Helper to create LB, listener, and pool for member tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "member-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-member-lb",
            vip_subnet_id=subnet.id,
        )

        listener = openstack_connection.load_balancer.create_listener(
            name="test-member-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )

        pool = openstack_connection.load_balancer.create_pool(
            name="test-member-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )

        return lb, listener, pool, subnet

    def test_list_members(self, openstack_connection: Connection) -> None:
        """Test listing pool members."""
        lb, listener, pool, subnet = self._create_pool(openstack_connection)
        members = list(openstack_connection.load_balancer.members(pool.id))
        # May be empty initially
        assert isinstance(members, list)

    def test_create_member(self, openstack_connection: Connection) -> None:
        """Test creating a pool member."""
        lb, listener, pool, subnet = self._create_pool(openstack_connection)

        member = openstack_connection.load_balancer.create_member(
            pool.id,
            name="test-sdk-member",
            address="10.0.0.10",
            protocol_port=8080,
            subnet_id=subnet.id,
        )
        assert member is not None
        assert member.name == "test-sdk-member"
        assert member.address == "10.0.0.10"
        assert member.protocol_port == 8080

    def test_get_member(self, openstack_connection: Connection) -> None:
        """Test getting a specific pool member."""
        lb, listener, pool, subnet = self._create_pool(openstack_connection)
        member = openstack_connection.load_balancer.create_member(
            pool.id,
            name="test-get-member",
            address="10.0.0.11",
            protocol_port=8080,
            subnet_id=subnet.id,
        )

        fetched = openstack_connection.load_balancer.get_member(member.id, pool.id)
        assert fetched is not None
        assert fetched.id == member.id

    def test_update_member(self, openstack_connection: Connection) -> None:
        """Test updating a pool member."""
        lb, listener, pool, subnet = self._create_pool(openstack_connection)
        member = openstack_connection.load_balancer.create_member(
            pool.id,
            name="test-update-member",
            address="10.0.0.12",
            protocol_port=8080,
            subnet_id=subnet.id,
        )

        updated = openstack_connection.load_balancer.update_member(
            member.id,
            pool.id,
            weight=5,
        )
        assert updated.weight == 5

    def test_delete_member(self, openstack_connection: Connection) -> None:
        """Test deleting a pool member."""
        lb, listener, pool, subnet = self._create_pool(openstack_connection)
        member = openstack_connection.load_balancer.create_member(
            pool.id,
            name="test-delete-member",
            address="10.0.0.13",
            protocol_port=8080,
            subnet_id=subnet.id,
        )

        result = openstack_connection.load_balancer.delete_member(member.id, pool.id)
        assert result is None


class TestOctaviaHealthMonitors:
    """Test Octavia health monitor operations via SDK."""

    def _create_pool(self, openstack_connection: Connection) -> object:
        """Helper to create LB, listener, and pool for health monitor tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "hm-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-hm-lb",
            vip_subnet_id=subnet.id,
        )

        listener = openstack_connection.load_balancer.create_listener(
            name="test-hm-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )

        pool = openstack_connection.load_balancer.create_pool(
            name="test-hm-pool",
            listener_id=listener.id,
            protocol="HTTP",
            lb_algorithm="ROUND_ROBIN",
        )

        return pool

    def test_list_health_monitors(self, openstack_connection: Connection) -> None:
        """Test listing health monitors."""
        monitors = list(openstack_connection.load_balancer.health_monitors())
        # May be empty initially
        assert isinstance(monitors, list)

    def test_create_health_monitor(self, openstack_connection: Connection) -> None:
        """Test creating a health monitor."""
        pool = self._create_pool(openstack_connection)

        monitor = openstack_connection.load_balancer.create_health_monitor(
            name="test-sdk-hm",
            pool_id=pool.id,
            type="HTTP",
            delay=5,
            timeout=10,
            max_retries=3,
        )
        assert monitor is not None
        assert monitor.name == "test-sdk-hm"
        assert monitor.type == "HTTP"
        assert monitor.delay == 5

    def test_get_health_monitor(self, openstack_connection: Connection) -> None:
        """Test getting a specific health monitor."""
        pool = self._create_pool(openstack_connection)
        monitor = openstack_connection.load_balancer.create_health_monitor(
            name="test-get-hm",
            pool_id=pool.id,
            type="HTTP",
            delay=5,
            timeout=10,
            max_retries=3,
        )

        fetched = openstack_connection.load_balancer.get_health_monitor(monitor.id)
        assert fetched is not None
        assert fetched.id == monitor.id

    def test_update_health_monitor(self, openstack_connection: Connection) -> None:
        """Test updating a health monitor."""
        pool = self._create_pool(openstack_connection)
        monitor = openstack_connection.load_balancer.create_health_monitor(
            name="test-update-hm",
            pool_id=pool.id,
            type="HTTP",
            delay=5,
            timeout=10,
            max_retries=3,
        )

        updated = openstack_connection.load_balancer.update_health_monitor(
            monitor.id,
            delay=10,
        )
        assert updated.delay == 10

    def test_delete_health_monitor(self, openstack_connection: Connection) -> None:
        """Test deleting a health monitor."""
        pool = self._create_pool(openstack_connection)
        monitor = openstack_connection.load_balancer.create_health_monitor(
            name="test-delete-hm",
            pool_id=pool.id,
            type="HTTP",
            delay=5,
            timeout=10,
            max_retries=3,
        )

        openstack_connection.load_balancer.delete_health_monitor(monitor.id)
        # Verify deletion
        deleted = openstack_connection.load_balancer.find_health_monitor(monitor.id)
        assert deleted is None


class TestOctaviaL7Policies:
    """Test Octavia L7 policy operations via SDK."""

    def _create_listener(self, openstack_connection: Connection) -> tuple:
        """Helper to create LB and listener for L7 policy tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "l7-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-l7-lb",
            vip_subnet_id=subnet.id,
        )

        listener = openstack_connection.load_balancer.create_listener(
            name="test-l7-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )

        return lb, listener

    def test_list_l7_policies(self, openstack_connection: Connection) -> None:
        """Test listing L7 policies."""
        policies = list(openstack_connection.load_balancer.l7_policies())
        # May be empty initially
        assert isinstance(policies, list)

    def test_create_l7_policy(self, openstack_connection: Connection) -> None:
        """Test creating an L7 policy."""
        lb, listener = self._create_listener(openstack_connection)

        policy = openstack_connection.load_balancer.create_l7_policy(
            name="test-sdk-l7policy",
            listener_id=listener.id,
            action="REJECT",
            position=1,
        )
        assert policy is not None
        assert policy.name == "test-sdk-l7policy"
        assert policy.action == "REJECT"

    def test_get_l7_policy(self, openstack_connection: Connection) -> None:
        """Test getting a specific L7 policy."""
        lb, listener = self._create_listener(openstack_connection)
        policy = openstack_connection.load_balancer.create_l7_policy(
            name="test-get-l7policy",
            listener_id=listener.id,
            action="REJECT",
            position=1,
        )

        fetched = openstack_connection.load_balancer.get_l7_policy(policy.id)
        assert fetched is not None
        assert fetched.id == policy.id

    def test_update_l7_policy(self, openstack_connection: Connection) -> None:
        """Test updating an L7 policy."""
        lb, listener = self._create_listener(openstack_connection)
        policy = openstack_connection.load_balancer.create_l7_policy(
            name="test-update-l7policy",
            listener_id=listener.id,
            action="REJECT",
            position=1,
        )

        updated = openstack_connection.load_balancer.update_l7_policy(
            policy.id,
            description="Updated L7 policy",
        )
        assert updated.description == "Updated L7 policy"

    def test_delete_l7_policy(self, openstack_connection: Connection) -> None:
        """Test deleting an L7 policy."""
        lb, listener = self._create_listener(openstack_connection)
        policy = openstack_connection.load_balancer.create_l7_policy(
            name="test-delete-l7policy",
            listener_id=listener.id,
            action="REJECT",
            position=1,
        )

        result = openstack_connection.load_balancer.delete_l7_policy(policy.id)
        assert result is None


class TestOctaviaL7Rules:
    """Test Octavia L7 rule operations via SDK."""

    def _create_l7_policy(self, openstack_connection: Connection) -> tuple:
        """Helper to create LB, listener, and L7 policy for L7 rule tests."""
        network, subnet = _create_network_and_subnet(openstack_connection, "l7rule-lb")

        lb = openstack_connection.load_balancer.create_load_balancer(
            name="test-l7rule-lb",
            vip_subnet_id=subnet.id,
        )

        listener = openstack_connection.load_balancer.create_listener(
            name="test-l7rule-listener",
            loadbalancer_id=lb.id,
            protocol="HTTP",
            protocol_port=80,
        )

        policy = openstack_connection.load_balancer.create_l7_policy(
            name="test-l7rule-policy",
            listener_id=listener.id,
            action="REJECT",
            position=1,
        )

        return lb, listener, policy

    def test_list_l7_rules(self, openstack_connection: Connection) -> None:
        """Test listing L7 rules."""
        lb, listener, policy = self._create_l7_policy(openstack_connection)
        rules = list(openstack_connection.load_balancer.l7_rules(policy.id))
        # May be empty initially
        assert isinstance(rules, list)

    def test_create_l7_rule(self, openstack_connection: Connection) -> None:
        """Test creating an L7 rule."""
        lb, listener, policy = self._create_l7_policy(openstack_connection)

        rule = openstack_connection.load_balancer.create_l7_rule(
            policy.id,
            type="PATH",
            compare_type="STARTS_WITH",
            rule_value="/api",
        )
        assert rule is not None
        assert rule.type == "PATH"
        assert rule.compare_type == "STARTS_WITH"
        assert rule.rule_value == "/api"

    def test_get_l7_rule(self, openstack_connection: Connection) -> None:
        """Test getting a specific L7 rule."""
        lb, listener, policy = self._create_l7_policy(openstack_connection)
        rule = openstack_connection.load_balancer.create_l7_rule(
            policy.id,
            type="PATH",
            compare_type="STARTS_WITH",
            rule_value="/test",
        )

        fetched = openstack_connection.load_balancer.get_l7_rule(rule.id, policy.id)
        assert fetched is not None
        assert fetched.id == rule.id

    def test_update_l7_rule(self, openstack_connection: Connection) -> None:
        """Test updating an L7 rule."""
        lb, listener, policy = self._create_l7_policy(openstack_connection)
        rule = openstack_connection.load_balancer.create_l7_rule(
            policy.id,
            type="PATH",
            compare_type="STARTS_WITH",
            rule_value="/old",
        )

        updated = openstack_connection.load_balancer.update_l7_rule(
            rule.id,
            policy.id,
            rule_value="/new",
        )
        assert updated.rule_value == "/new"

    def test_delete_l7_rule(self, openstack_connection: Connection) -> None:
        """Test deleting an L7 rule."""
        lb, listener, policy = self._create_l7_policy(openstack_connection)
        rule = openstack_connection.load_balancer.create_l7_rule(
            policy.id,
            type="PATH",
            compare_type="STARTS_WITH",
            rule_value="/delete",
        )

        openstack_connection.load_balancer.delete_l7_rule(rule.id, policy.id)
        # Verify deletion by trying to list rules for the policy
        rules = list(openstack_connection.load_balancer.l7_rules(policy.id))
        assert not any(r.id == rule.id for r in rules)
