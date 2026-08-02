"""SDK tests for Neutron security groups multi-tenant isolation.

Tests that security groups are properly isolated between tenants and that
each tenant has its own default security group.
"""

import openstack
import pytest
from openstack.connection import Connection
from openstack.exceptions import NotFoundException

from tests.conftest import grant_scope


class TestSecurityGroupTenantIsolation:
    """Test security group tenant/project isolation."""

    @pytest.fixture
    def tenant1_connection(self, emulator_servers) -> Connection:
        """Create an OpenStack connection for tenant1."""
        # First create the project in Keystone
        admin_conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="admin",
            password="secret",
            project_name="admin",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
        )

        # Create tenant1 project
        project1 = admin_conn.identity.create_project(
            name="tenant1",
            domain_id="default",
            description="Tenant 1 for testing",
        )

        # Create a user for tenant1
        admin_conn.identity.create_user(
            name="user1",
            password="secret1",
            domain_id="default",
            default_project_id=project1.id,
        )
        # Keystone will not scope a token to a project the user holds no
        # role on, so grant it the way an operator would.
        grant_scope(project_id=project1.id, user_name="user1")
        admin_conn.close()

        # Connect as tenant1
        conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="user1",
            password="secret1",
            project_name="tenant1",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
            network_endpoint_override=emulator_servers.get_url("neutron"),
        )
        yield conn
        conn.close()

    @pytest.fixture
    def tenant2_connection(self, emulator_servers) -> Connection:
        """Create an OpenStack connection for tenant2."""
        # First create the project in Keystone
        admin_conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="admin",
            password="secret",
            project_name="admin",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
        )

        # Create tenant2 project
        project2 = admin_conn.identity.create_project(
            name="tenant2",
            domain_id="default",
            description="Tenant 2 for testing",
        )

        # Create a user for tenant2
        admin_conn.identity.create_user(
            name="user2",
            password="secret2",
            domain_id="default",
            default_project_id=project2.id,
        )
        # Keystone will not scope a token to a project the user holds no
        # role on, so grant it the way an operator would.
        grant_scope(project_id=project2.id, user_name="user2")
        admin_conn.close()

        # Connect as tenant2
        conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="user2",
            password="secret2",
            project_name="tenant2",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
            network_endpoint_override=emulator_servers.get_url("neutron"),
        )
        yield conn
        conn.close()

    def test_each_tenant_has_own_default_security_group(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that each tenant gets their own default security group."""
        # List security groups for tenant1
        tenant1_sgs = list(tenant1_connection.network.security_groups())
        tenant1_default = next((sg for sg in tenant1_sgs if sg.name == "default"), None)
        assert tenant1_default is not None
        tenant1_project_id = tenant1_default.project_id

        # List security groups for tenant2
        tenant2_sgs = list(tenant2_connection.network.security_groups())
        tenant2_default = next((sg for sg in tenant2_sgs if sg.name == "default"), None)
        assert tenant2_default is not None
        tenant2_project_id = tenant2_default.project_id

        # Each tenant should have their own default security group
        assert tenant1_default.id != tenant2_default.id
        assert tenant1_project_id != tenant2_project_id

    def test_tenant_cannot_see_other_tenant_security_groups(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot list another tenant's security groups."""
        # Create a security group in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-private-sg",
            description="Private to tenant1",
        )

        # Create a security group in tenant2
        sg2 = tenant2_connection.network.create_security_group(
            name="tenant2-private-sg",
            description="Private to tenant2",
        )

        # Tenant1 should only see their security groups
        tenant1_sgs = list(tenant1_connection.network.security_groups())
        tenant1_sg_ids = [sg.id for sg in tenant1_sgs]
        assert sg1.id in tenant1_sg_ids
        assert sg2.id not in tenant1_sg_ids

        # Tenant2 should only see their security groups
        tenant2_sgs = list(tenant2_connection.network.security_groups())
        tenant2_sg_ids = [sg.id for sg in tenant2_sgs]
        assert sg2.id in tenant2_sg_ids
        assert sg1.id not in tenant2_sg_ids

    def test_tenant_cannot_get_other_tenant_security_group(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot get another tenant's security group by ID."""
        # Create a security group in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-get-test",
        )

        # Tenant2 should not be able to get tenant1's security group
        with pytest.raises(NotFoundException):
            tenant2_connection.network.get_security_group(sg1.id)

    def test_tenant_cannot_update_other_tenant_security_group(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot update another tenant's security group."""
        # Create a security group in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-update-test",
            description="Original description",
        )

        # Tenant2 should not be able to update tenant1's security group
        with pytest.raises(NotFoundException):
            tenant2_connection.network.update_security_group(
                sg1.id,
                description="Modified by tenant2",
            )

        # Verify the description was not changed
        sg1_updated = tenant1_connection.network.get_security_group(sg1.id)
        assert sg1_updated.description == "Original description"

    def test_tenant_cannot_delete_other_tenant_security_group(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot delete another tenant's security group."""
        # Create a security group in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-delete-test",
        )

        # Tenant2 should not be able to delete tenant1's security group
        # The SDK raises an exception when delete fails
        with pytest.raises(Exception):
            tenant2_connection.network.delete_security_group(sg1.id)

        # Verify the security group still exists
        sg1_check = tenant1_connection.network.get_security_group(sg1.id)
        assert sg1_check is not None


class TestSecurityGroupRuleTenantIsolation:
    """Test security group rule tenant/project isolation."""

    @pytest.fixture
    def tenant1_connection(self, emulator_servers) -> Connection:
        """Create an OpenStack connection for tenant1."""
        admin_conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="admin",
            password="secret",
            project_name="admin",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
        )

        project1 = admin_conn.identity.create_project(
            name="tenant1_rules",
            domain_id="default",
        )
        admin_conn.identity.create_user(
            name="user1_rules",
            password="secret1",
            domain_id="default",
            default_project_id=project1.id,
        )
        # Scoping requires a real assignment, as against a real Keystone.
        grant_scope(project_id=project1.id, user_name="user1_rules")
        admin_conn.close()

        conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="user1_rules",
            password="secret1",
            project_name="tenant1_rules",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
            network_endpoint_override=emulator_servers.get_url("neutron"),
        )
        yield conn
        conn.close()

    @pytest.fixture
    def tenant2_connection(self, emulator_servers) -> Connection:
        """Create an OpenStack connection for tenant2."""
        admin_conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="admin",
            password="secret",
            project_name="admin",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
        )

        project2 = admin_conn.identity.create_project(
            name="tenant2_rules",
            domain_id="default",
        )
        admin_conn.identity.create_user(
            name="user2_rules",
            password="secret2",
            domain_id="default",
            default_project_id=project2.id,
        )
        # Scoping requires a real assignment, as against a real Keystone.
        grant_scope(project_id=project2.id, user_name="user2_rules")
        admin_conn.close()

        conn = openstack.connect(
            auth_type="password",
            auth_url=emulator_servers.get_url("keystone") + "/v3",
            username="user2_rules",
            password="secret2",
            project_name="tenant2_rules",
            project_domain_name="Default",
            user_domain_name="Default",
            region_name="RegionOne",
            identity_endpoint_override=emulator_servers.get_url("keystone") + "/v3",
            network_endpoint_override=emulator_servers.get_url("neutron"),
        )
        yield conn
        conn.close()

    def test_tenant_cannot_create_rule_in_other_tenant_security_group(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot create rules in another's security group."""
        # Create a security group in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-for-rules",
        )

        # Tenant2 should not be able to create a rule in tenant1's security group
        with pytest.raises(NotFoundException):
            tenant2_connection.network.create_security_group_rule(
                security_group_id=sg1.id,
                direction="ingress",
                protocol="tcp",
                port_range_min=22,
                port_range_max=22,
            )

    def test_tenant_cannot_see_other_tenant_security_group_rules(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot list another tenant's security group rules."""
        # Create a security group and rule in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-with-rules",
        )
        rule1 = tenant1_connection.network.create_security_group_rule(
            security_group_id=sg1.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=443,
            port_range_max=443,
        )

        # Tenant2 should not see tenant1's rules
        tenant2_rules = list(tenant2_connection.network.security_group_rules())
        tenant2_rule_ids = [r.id for r in tenant2_rules]
        assert rule1.id not in tenant2_rule_ids

    def test_tenant_cannot_get_other_tenant_security_group_rule(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot get another tenant's security group rule."""
        # Create a security group and rule in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-rule-get-test",
        )
        rule1 = tenant1_connection.network.create_security_group_rule(
            security_group_id=sg1.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=80,
            port_range_max=80,
        )

        # Tenant2 should not be able to get tenant1's rule
        with pytest.raises(NotFoundException):
            tenant2_connection.network.get_security_group_rule(rule1.id)

    def test_tenant_cannot_delete_other_tenant_security_group_rule(
        self,
        tenant1_connection: Connection,
        tenant2_connection: Connection,
    ) -> None:
        """Test that one tenant cannot delete another tenant's security group rule."""
        # Create a security group and rule in tenant1
        sg1 = tenant1_connection.network.create_security_group(
            name="tenant1-sg-rule-delete-test",
        )
        rule1 = tenant1_connection.network.create_security_group_rule(
            security_group_id=sg1.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=8080,
            port_range_max=8080,
        )

        # Tenant2 should not be able to delete tenant1's rule
        # The SDK may not raise an exception on 404 for delete operations
        # but the rule should still exist afterwards
        try:
            tenant2_connection.network.delete_security_group_rule(rule1.id)
        except NotFoundException:
            pass  # Expected behavior

        # Verify the rule still exists - this is the key assertion
        rule1_check = tenant1_connection.network.get_security_group_rule(rule1.id)
        assert rule1_check is not None, "Rule was deleted by another tenant!"

    def test_default_security_group_has_egress_rules(
        self,
        tenant1_connection: Connection,
    ) -> None:
        """Test that the default security group has default egress rules."""
        # List security groups to trigger default creation
        sgs = list(tenant1_connection.network.security_groups())
        default_sg = next((sg for sg in sgs if sg.name == "default"), None)
        assert default_sg is not None

        # Get rules for the default security group
        rules = list(
            tenant1_connection.network.security_group_rules(security_group_id=default_sg.id)
        )

        # Should have at least 2 egress rules (IPv4 and IPv6)
        egress_rules = [r for r in rules if r.direction == "egress"]
        assert len(egress_rules) >= 2

        # Check for IPv4 and IPv6 egress rules
        ethertypes = [r.ether_type for r in egress_rules]
        assert "IPv4" in ethertypes
        assert "IPv6" in ethertypes


class TestSecurityGroupRuleCreation:
    """Test security group rule creation scenarios."""

    def test_create_ssh_ingress_rule(self, openstack_connection: Connection) -> None:
        """Test creating an SSH ingress rule."""
        sg = openstack_connection.network.create_security_group(
            name="test-ssh-rule-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=22,
            port_range_max=22,
            remote_ip_prefix="0.0.0.0/0",
        )

        assert rule.direction == "ingress"
        assert rule.protocol == "tcp"
        assert rule.port_range_min == 22
        assert rule.port_range_max == 22
        assert rule.remote_ip_prefix == "0.0.0.0/0"

    def test_create_http_https_rules(self, openstack_connection: Connection) -> None:
        """Test creating HTTP and HTTPS ingress rules."""
        sg = openstack_connection.network.create_security_group(
            name="test-web-rules-sg",
        )

        # HTTP rule
        http_rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=80,
            port_range_max=80,
        )
        assert http_rule.port_range_min == 80

        # HTTPS rule
        https_rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=443,
            port_range_max=443,
        )
        assert https_rule.port_range_min == 443

    def test_create_icmp_rule(self, openstack_connection: Connection) -> None:
        """Test creating an ICMP rule (for ping)."""
        sg = openstack_connection.network.create_security_group(
            name="test-icmp-rule-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="icmp",
        )

        assert rule.protocol == "icmp"

    def test_create_port_range_rule(self, openstack_connection: Connection) -> None:
        """Test creating a rule with a port range."""
        sg = openstack_connection.network.create_security_group(
            name="test-port-range-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=8000,
            port_range_max=9000,
        )

        assert rule.port_range_min == 8000
        assert rule.port_range_max == 9000

    def test_create_udp_rule(self, openstack_connection: Connection) -> None:
        """Test creating a UDP rule."""
        sg = openstack_connection.network.create_security_group(
            name="test-udp-rule-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="udp",
            port_range_min=53,
            port_range_max=53,
        )

        assert rule.protocol == "udp"
        assert rule.port_range_min == 53

    def test_create_egress_rule(self, openstack_connection: Connection) -> None:
        """Test creating a custom egress rule."""
        sg = openstack_connection.network.create_security_group(
            name="test-egress-rule-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="egress",
            protocol="tcp",
            port_range_min=443,
            port_range_max=443,
            remote_ip_prefix="10.0.0.0/8",
        )

        assert rule.direction == "egress"
        assert rule.remote_ip_prefix == "10.0.0.0/8"

    def test_create_ipv6_rule(self, openstack_connection: Connection) -> None:
        """Test creating an IPv6 rule."""
        sg = openstack_connection.network.create_security_group(
            name="test-ipv6-rule-sg",
        )

        rule = openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            ethertype="IPv6",
            protocol="tcp",
            port_range_min=22,
            port_range_max=22,
            remote_ip_prefix="::/0",
        )

        assert rule.ether_type == "IPv6"
        assert rule.remote_ip_prefix == "::/0"

    def test_security_group_rules_listed_in_group(self, openstack_connection: Connection) -> None:
        """Test that rules are properly listed in the security group."""
        sg = openstack_connection.network.create_security_group(
            name="test-rules-in-group-sg",
        )

        # Create a few rules
        openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=22,
            port_range_max=22,
        )
        openstack_connection.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=80,
            port_range_max=80,
        )

        # Get the security group and check its rules
        sg_updated = openstack_connection.network.get_security_group(sg.id)

        # Should have the default egress rules plus our 2 new rules
        assert len(sg_updated.security_group_rules) >= 4

        # Find our SSH and HTTP rules
        rule_ports = [r.get("port_range_min") for r in sg_updated.security_group_rules]
        assert 22 in rule_ports
        assert 80 in rule_ports
