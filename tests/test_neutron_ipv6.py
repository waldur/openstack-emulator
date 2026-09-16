"""Tests for IPv6 and dual-stack behaviour in the Neutron and Octavia emulators.

Covers what a client driving an IPv6-only or dual-stack cloud depends on: the
subnet address modes, addresses derived from a prefix rather than a pool,
per-family allocation, and the refusals that make the negative paths testable
without a real Neutron.
"""

import ipaddress

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db, eui64_address

V6_CIDR = "2001:db8:1::/64"


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    db.reset_neutron()
    db.reset_octavia()
    yield


_apps = create_all_service_apps()
client = TestClient(_apps["neutron"])
octavia_client = TestClient(_apps["octavia"])


def make_network(name):
    return client.post("/v2.0/networks", json={"network": {"name": name}}).json()["network"]["id"]


def make_subnet(network_id, cidr, **extra):
    payload = {"network_id": network_id, "cidr": cidr}
    payload.update(extra)
    if ":" in cidr:
        payload.setdefault("ip_version", 6)
    return client.post("/v2.0/subnets", json={"subnet": payload})


def make_slaac_subnet(network_id, cidr=V6_CIDR):
    response = make_subnet(network_id, cidr, ipv6_ra_mode="slaac", ipv6_address_mode="slaac")
    assert response.status_code == 201, response.text
    return response.json()["subnet"]


class TestIpv6Subnets:
    """Subnet creation carries the IPv6 address modes, and validates them."""

    def test_create_slaac_subnet(self):
        """The modes round-trip, and the subnet is usable straight away."""
        network_id = make_network("v6-net")
        subnet = make_slaac_subnet(network_id)

        assert subnet["ip_version"] == 6
        assert subnet["ipv6_ra_mode"] == "slaac"
        assert subnet["ipv6_address_mode"] == "slaac"
        assert subnet["cidr"] == V6_CIDR

    def test_ipv6_subnet_gets_a_gateway_and_a_pool(self):
        """Both are derived from the prefix, not parsed as IPv4.

        A client will not attach a router to a subnet that reports no gateway,
        so an IPv6 subnet without one is effectively unusable.
        """
        network_id = make_network("v6-gw-net")
        subnet = make_slaac_subnet(network_id)

        prefix = ipaddress.ip_network(V6_CIDR)
        assert ipaddress.ip_address(subnet["gateway_ip"]) in prefix
        assert subnet["gateway_ip"] == "2001:db8:1::1"

        (pool,) = subnet["allocation_pools"]
        assert ipaddress.ip_address(pool["start"]) in prefix
        assert ipaddress.ip_address(pool["end"]) in prefix
        # The gateway is not handed out again.
        assert pool["start"] != subnet["gateway_ip"]

    def test_stateful_subnet_does_not_need_a_64_prefix(self):
        """Only the prefix-derived modes carry the /64 constraint."""
        network_id = make_network("v6-stateful-net")
        response = make_subnet(network_id, "2001:db8:2::/56", ipv6_ra_mode="dhcpv6-stateful")
        assert response.status_code == 201, response.text
        assert response.json()["subnet"]["ipv6_ra_mode"] == "dhcpv6-stateful"

    @pytest.mark.parametrize("mode", ["slaac", "dhcpv6-stateless"])
    def test_prefix_addressed_subnet_requires_a_64(self, mode):
        """SLAAC and stateless build a 64-bit interface id, so /64 it must be."""
        network_id = make_network(f"v6-short-{mode}")
        response = make_subnet(network_id, "2001:db8:3::/56", ipv6_address_mode=mode)

        assert response.status_code == 400, response.text
        error = response.json()["NeutronError"]
        assert error["type"] == "InvalidInput"
        assert "/64" in error["message"]

    def test_mode_on_an_ipv4_subnet_is_rejected(self):
        """The modes are meaningless for IPv4 and Neutron says so."""
        network_id = make_network("v4-mode-net")
        response = make_subnet(network_id, "10.0.0.0/24", ip_version=4, ipv6_ra_mode="slaac")

        assert response.status_code == 400, response.text
        error = response.json()["NeutronError"]
        assert error["type"] == "InvalidInput"
        assert error["message"] == "ipv6_ra_mode is not valid when ip_version is 4"

    def test_unknown_mode_is_rejected(self):
        """dhcpv6-pd and friends are not among the accepted values."""
        network_id = make_network("v6-badmode-net")
        response = make_subnet(V6_CIDR and network_id, V6_CIDR, ipv6_ra_mode="dhcpv6-pd")

        assert response.status_code == 400, response.text
        assert response.json()["NeutronError"]["type"] == "InvalidInput"

    @pytest.mark.parametrize("attribute", ["ipv6_ra_mode", "ipv6_address_mode"])
    def test_modes_are_immutable(self, attribute):
        """Both are read-only after creation, so a PUT naming one is refused."""
        network_id = make_network(f"v6-immutable-{attribute}")
        subnet = make_slaac_subnet(network_id)

        response = client.put(
            f"/v2.0/subnets/{subnet['id']}",
            json={"subnet": {attribute: "dhcpv6-stateful"}},
        )
        assert response.status_code == 400, response.text
        error = response.json()["NeutronError"]
        assert error["message"] == f"Cannot update read-only attribute {attribute}"

        # And nothing changed.
        unchanged = client.get(f"/v2.0/subnets/{subnet['id']}").json()["subnet"]
        assert unchanged[attribute] == "slaac"

    def test_an_ordinary_update_still_works_on_an_ipv6_subnet(self):
        """Refusing the modes must not refuse the rest of the body."""
        network_id = make_network("v6-rename-net")
        subnet = make_slaac_subnet(network_id)

        response = client.put(f"/v2.0/subnets/{subnet['id']}", json={"subnet": {"name": "renamed"}})
        assert response.status_code == 200, response.text
        assert response.json()["subnet"]["name"] == "renamed"


class TestPrefixDerivedPorts:
    """Ports on SLAAC/stateless subnets get an address built from the prefix."""

    def test_port_address_is_derived_from_the_prefix_and_mac(self):
        """The address is the modified EUI-64, and it sits inside the prefix."""
        network_id = make_network("slaac-port-net")
        subnet = make_slaac_subnet(network_id)

        port = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "name": "slaac-port",
                    "network_id": network_id,
                    "fixed_ips": [{"subnet_id": subnet["id"]}],
                }
            },
        ).json()["port"]

        (fixed_ip,) = port["fixed_ips"]
        assert fixed_ip["subnet_id"] == subnet["id"]
        assert fixed_ip["ip_address"] == eui64_address(V6_CIDR, port["mac_address"])
        assert ipaddress.ip_address(fixed_ip["ip_address"]) in ipaddress.ip_network(V6_CIDR)

    def test_two_ports_get_different_addresses(self):
        """Derived or not, two ports must not collide."""
        network_id = make_network("slaac-two-net")
        subnet = make_slaac_subnet(network_id)

        def create():
            return client.post(
                "/v2.0/ports",
                json={
                    "port": {
                        "network_id": network_id,
                        "fixed_ips": [{"subnet_id": subnet["id"]}],
                    }
                },
            ).json()["port"]["fixed_ips"][0]["ip_address"]

        assert create() != create()

    def test_pinning_an_address_is_refused(self):
        """Neutron will not let a caller choose an address on such a subnet."""
        network_id = make_network("slaac-pin-net")
        subnet = make_slaac_subnet(network_id)

        response = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": network_id,
                    "fixed_ips": [{"subnet_id": subnet["id"], "ip_address": "2001:db8:1::99"}],
                }
            },
        )
        assert response.status_code == 400, response.text
        error = response.json()["NeutronError"]
        assert error["type"] == "InvalidInput"
        assert "configured for automatic addresses" in error["message"]

    def test_pinning_an_address_on_a_stateful_subnet_is_allowed(self):
        """dhcpv6-stateful allocates from a pool, so an address may be chosen."""
        network_id = make_network("stateful-pin-net")
        subnet = make_subnet(network_id, "2001:db8:4::/64", ipv6_ra_mode="dhcpv6-stateful").json()[
            "subnet"
        ]

        response = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": network_id,
                    "fixed_ips": [{"subnet_id": subnet["id"], "ip_address": "2001:db8:4::99"}],
                }
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["port"]["fixed_ips"][0]["ip_address"] == "2001:db8:4::99"

    def test_resending_the_existing_address_is_accepted(self):
        """A client reads the list, edits one entry and sends it all back.

        The SLAAC entry it read carries an address, so refusing every named
        address here would break the only update shape Neutron offers.
        """
        network_id = make_network("slaac-resend-net")
        subnet = make_slaac_subnet(network_id)
        port = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": network_id,
                    "fixed_ips": [{"subnet_id": subnet["id"]}],
                }
            },
        ).json()["port"]
        derived = port["fixed_ips"][0]["ip_address"]

        response = client.put(
            f"/v2.0/ports/{port['id']}",
            json={"port": {"fixed_ips": [{"subnet_id": subnet["id"], "ip_address": derived}]}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["port"]["fixed_ips"] == [
            {"subnet_id": subnet["id"], "ip_address": derived}
        ]


class TestDualStack:
    """A network carrying both families gives out one address of each."""

    def _dual_stack_network(self, name):
        network_id = make_network(name)
        v4 = make_subnet(network_id, "10.20.0.0/24").json()["subnet"]
        v6 = make_slaac_subnet(network_id)
        return network_id, v4, v6

    def test_port_gets_an_address_of_each_family(self):
        """Stopping at the first subnet would leave the port half-addressed."""
        network_id, v4, v6 = self._dual_stack_network("dual-port-net")

        port = client.post("/v2.0/ports", json={"port": {"network_id": network_id}}).json()["port"]

        by_subnet = {ip["subnet_id"]: ip["ip_address"] for ip in port["fixed_ips"]}
        assert set(by_subnet) == {v4["id"], v6["id"]}
        assert ipaddress.ip_address(by_subnet[v4["id"]]).version == 4
        assert ipaddress.ip_address(by_subnet[v6["id"]]).version == 6

    def test_update_replaces_the_whole_list(self):
        """An address left out of the list is released, as in Neutron."""
        network_id, v4, _ = self._dual_stack_network("dual-replace-net")
        port = client.post("/v2.0/ports", json={"port": {"network_id": network_id}}).json()["port"]

        response = client.put(
            f"/v2.0/ports/{port['id']}",
            json={"port": {"fixed_ips": [{"subnet_id": v4["id"]}]}},
        )
        assert response.status_code == 200, response.text
        assert [ip["subnet_id"] for ip in response.json()["port"]["fixed_ips"]] == [v4["id"]]

    def test_changing_one_family_keeps_the_other(self):
        """The shape a dual-stack client actually sends: read, edit one, resend."""
        network_id, v4, v6 = self._dual_stack_network("dual-keep-net")
        port = client.post("/v2.0/ports", json={"port": {"network_id": network_id}}).json()["port"]
        current = {ip["subnet_id"]: ip["ip_address"] for ip in port["fixed_ips"]}

        response = client.put(
            f"/v2.0/ports/{port['id']}",
            json={
                "port": {
                    "fixed_ips": [
                        {"subnet_id": v4["id"], "ip_address": "10.20.0.77"},
                        {"subnet_id": v6["id"], "ip_address": current[v6["id"]]},
                    ]
                }
            },
        )
        assert response.status_code == 200, response.text
        updated = {ip["subnet_id"]: ip["ip_address"] for ip in response.json()["port"]["fixed_ips"]}
        assert updated[v4["id"]] == "10.20.0.77"
        assert updated[v6["id"]] == current[v6["id"]]


class TestIpv6RouterInterfaces:
    """A router attaches to an IPv6 subnet by subnet or by port."""

    def test_add_interface_by_subnet(self):
        """The subnet-only form is what the provisioning path uses."""
        network_id = make_network("v6-iface-net")
        subnet = make_slaac_subnet(network_id)
        router_id = client.post("/v2.0/routers", json={"router": {"name": "v6-router"}}).json()[
            "router"
        ]["id"]

        response = client.put(
            f"/v2.0/routers/{router_id}/add_router_interface",
            json={"subnet_id": subnet["id"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["subnet_id"] == subnet["id"]

        ports = client.get(f"/v2.0/ports?device_id={router_id}").json()["ports"]
        (port,) = ports
        assert port["device_owner"] == "network:router_interface"
        # The interface holds the subnet's gateway, which is legitimate even on
        # a subnet whose tenant addresses come from the prefix.
        assert port["fixed_ips"][0]["ip_address"] == subnet["gateway_ip"]

    def test_add_interface_by_port_naming_only_the_subnet(self):
        """The port form, where the port was created with just a subnet_id."""
        network_id = make_network("v6-ifaceport-net")
        subnet = make_slaac_subnet(network_id)
        port = client.post(
            "/v2.0/ports",
            json={
                "port": {
                    "network_id": network_id,
                    "fixed_ips": [{"subnet_id": subnet["id"]}],
                }
            },
        ).json()["port"]
        router_id = client.post(
            "/v2.0/routers", json={"router": {"name": "v6-router-port"}}
        ).json()["router"]["id"]

        response = client.put(
            f"/v2.0/routers/{router_id}/add_router_interface",
            json={"port_id": port["id"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["subnet_id"] == subnet["id"]

    def test_dual_stack_gateway_holds_both_families(self):
        """external_fixed_ips carries one address per family."""
        network_id = client.post(
            "/v2.0/networks",
            json={"network": {"name": "dual-ext", "router:external": True}},
        ).json()["network"]["id"]
        v4 = make_subnet(network_id, "198.51.100.0/24").json()["subnet"]
        v6 = make_slaac_subnet(network_id)

        response = client.post(
            "/v2.0/routers",
            json={
                "router": {
                    "name": "dual-gw-router",
                    "external_gateway_info": {"network_id": network_id},
                }
            },
        )
        assert response.status_code == 201, response.text
        gateway = response.json()["router"]["external_gateway_info"]
        by_subnet = {ip["subnet_id"]: ip["ip_address"] for ip in gateway["external_fixed_ips"]}
        assert set(by_subnet) == {v4["id"], v6["id"]}
        assert ipaddress.ip_address(by_subnet[v6["id"]]).version == 6


class TestFloatingIpsAreIpv4Only:
    """Floating IPs map a single IPv4 address; IPv6 is routed instead."""

    def test_ipv6_only_external_network_is_rejected(self):
        """The refusal a client relies on to explain itself to an operator."""
        network_id = client.post(
            "/v2.0/networks",
            json={"network": {"name": "v6-only-ext", "router:external": True}},
        ).json()["network"]["id"]
        make_slaac_subnet(network_id)

        response = client.post(
            "/v2.0/floatingips", json={"floatingip": {"floating_network_id": network_id}}
        )
        assert response.status_code == 400, response.text
        assert "does not contain any IPv4 subnet" in response.json()["error"]["message"]

    def test_allocation_comes_from_the_ipv4_subnet(self):
        """On a dual-stack external network the IPv6 subnet is not a source."""
        network_id = client.post(
            "/v2.0/networks",
            json={"network": {"name": "dual-fip-ext", "router:external": True}},
        ).json()["network"]["id"]
        make_slaac_subnet(network_id)
        make_subnet(network_id, "198.51.101.0/24")

        response = client.post(
            "/v2.0/floatingips", json={"floatingip": {"floating_network_id": network_id}}
        )
        assert response.status_code == 201, response.text
        address = response.json()["floatingip"]["floating_ip_address"]
        assert ipaddress.ip_address(address).version == 4

    def test_association_picks_the_ports_ipv4_address(self):
        """A dual-stack port's first entry may be the IPv6 one."""
        external_id = client.post(
            "/v2.0/networks",
            json={"network": {"name": "assoc-ext", "router:external": True}},
        ).json()["network"]["id"]
        make_subnet(external_id, "198.51.102.0/24")

        tenant_id = make_network("assoc-tenant-net")
        make_slaac_subnet(tenant_id)
        v4 = make_subnet(tenant_id, "10.30.0.0/24").json()["subnet"]
        port = client.post("/v2.0/ports", json={"port": {"network_id": tenant_id}}).json()["port"]
        expected = next(ip["ip_address"] for ip in port["fixed_ips"] if ip["subnet_id"] == v4["id"])

        fip = client.post(
            "/v2.0/floatingips",
            json={"floatingip": {"floating_network_id": external_id, "port_id": port["id"]}},
        ).json()["floatingip"]

        assert fip["fixed_ip_address"] == expected
        assert ipaddress.ip_address(fip["fixed_ip_address"]).version == 4


class TestIpv6AllowedAddressPairs:
    """Pairs accept IPv6, but not multicast nor anything covering it."""

    def _port(self, name):
        network_id = make_network(name)
        make_slaac_subnet(network_id)
        return client.post("/v2.0/ports", json={"port": {"network_id": network_id}}).json()["port"]

    @pytest.mark.parametrize(
        "value", ["fd00:1::/64", "2001:db8:9::10", "fc00::/7", "192.168.250.0/24"]
    )
    def test_ordinary_pairs_are_accepted(self, value):
        """Almost everything is allowed: Neutron's own check is narrow."""
        port = self._port(f"aap-ok-{abs(hash(value))}")
        response = client.put(
            f"/v2.0/ports/{port['id']}",
            json={"port": {"allowed_address_pairs": [{"ip_address": value}]}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["port"]["allowed_address_pairs"] == [{"ip_address": value}]

    @pytest.mark.parametrize("value", ["ff02::1", "ff00::/8", "::/0", "224.0.0.1"])
    def test_multicast_and_anything_covering_it_is_refused(self, value):
        """``::/0`` is refused precisely because it covers ff00::/8."""
        port = self._port(f"aap-bad-{abs(hash(value))}")
        response = client.put(
            f"/v2.0/ports/{port['id']}",
            json={"port": {"allowed_address_pairs": [{"ip_address": value}]}},
        )
        assert response.status_code == 400, response.text
        assert response.json()["NeutronError"]["type"] == "InvalidInput"

        unchanged = client.get(f"/v2.0/ports/{port['id']}").json()["port"]
        assert unchanged["allowed_address_pairs"] == []

    def test_pairs_survive_a_round_trip_on_create(self):
        """A port may be created with pairs already set."""
        network_id = make_network("aap-create-net")
        make_slaac_subnet(network_id)
        pairs = [{"ip_address": "fd00:2::/64", "mac_address": "fa:16:3e:ab:cd:ef"}]

        response = client.post(
            "/v2.0/ports",
            json={"port": {"network_id": network_id, "allowed_address_pairs": pairs}},
        )
        assert response.status_code == 201, response.text
        assert response.json()["port"]["allowed_address_pairs"] == pairs


class TestIpv6LoadBalancerVip:
    """An IPv6 VIP subnet yields an IPv6 VIP."""

    def test_vip_is_allocated_from_an_ipv6_subnet(self):
        """Octavia picks the address, so its family follows the subnet's."""
        network_id = make_network("lb-v6-net")
        subnet = make_slaac_subnet(network_id)

        response = octavia_client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "v6-lb", "vip_subnet_id": subnet["id"]}},
        )
        assert response.status_code == 201, response.text
        vip = response.json()["loadbalancer"]["vip_address"]
        assert ipaddress.ip_address(vip).version == 6
        assert ipaddress.ip_address(vip) in ipaddress.ip_network(V6_CIDR)

    def test_vip_is_allocated_from_an_ipv4_subnet(self):
        """The IPv4 side keeps working, from the subnet rather than a counter."""
        network_id = make_network("lb-v4-net")
        subnet = make_subnet(network_id, "10.40.0.0/24").json()["subnet"]

        response = octavia_client.post(
            "/v2.0/lbaas/loadbalancers",
            json={"loadbalancer": {"name": "v4-lb", "vip_subnet_id": subnet["id"]}},
        )
        assert response.status_code == 201, response.text
        vip = response.json()["loadbalancer"]["vip_address"]
        assert ipaddress.ip_address(vip) in ipaddress.ip_network("10.40.0.0/24")

    def test_vip_without_a_subnet_still_works(self):
        """No VIP subnet named: the emulator falls back as it always did."""
        response = octavia_client.post(
            "/v2.0/lbaas/loadbalancers", json={"loadbalancer": {"name": "bare-lb"}}
        )
        assert response.status_code == 201, response.text
        assert response.json()["loadbalancer"]["vip_address"]
