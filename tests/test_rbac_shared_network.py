"""RBAC-shared networks: what a consuming tenant may and may not do.

Both rules here were established against RHOS 17, because the emulator disagreed
with it. A tenant handed a network through an ``access_as_shared`` RBAC policy
may build on it, but the network still belongs to someone else:

* pinning a specific IP is admin-or-network-owner
  (``create_port:fixed_ips:ip_address``), so the consuming tenant gets 403 —
  while the same request succeeds on its own network, succeeds without an
  ``ip_address``, and succeeds when an admin makes it on the tenant's behalf;
* the share cannot be revoked while the target project still has ports on the
  network — Neutron answers 409 until they are gone.

Getting the first one wrong is the dangerous case: code that pins IPs passes
against a permissive emulator and then fails in production.
"""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import scoped_token

CIDR = "10.90.0.0/24"
PINNED = "10.90.0.50"


@pytest.fixture
def apps():
    return create_all_service_apps()


@pytest.fixture(autouse=True)
def reset():
    db.reset_keystone()
    db.reset_neutron()


@pytest.fixture
def world():
    """Owner project with a network, and a consumer project it is shared to."""
    owner = db.create_project(name="net-owner", domain_id="default")
    consumer_token = scoped_token(project_name="consumer", role_name="member")
    consumer_id = db.validate_token(consumer_token.id).project_id
    network = db.create_network(name="shared-net", project_id=owner.id)
    subnet = db.create_subnet(network_id=network.id, cidr=CIDR, project_id=owner.id)
    db.create_rbac_policy(
        object_type="network",
        object_id=network.id,
        target_project=consumer_id,
        project_id=owner.id,
        action="access_as_shared",
    )
    return {
        "owner": owner,
        "network": network,
        "subnet": subnet,
        "consumer_id": consumer_id,
        "headers": {"X-Auth-Token": consumer_token.id},
        "admin": {"X-Auth-Token": scoped_token(project_name="admin", role_name="admin").id},
    }


def create_port(client, headers, **port):
    return client.post("/v2.0/ports", headers=headers, json={"port": port})


class TestPinningAnAddress:
    def test_consumer_may_not_pin_an_ip_on_a_shared_network(self, apps, world):
        client = TestClient(apps["neutron"])

        response = create_port(
            client,
            world["headers"],
            network_id=world["network"].id,
            fixed_ips=[{"subnet_id": world["subnet"].id, "ip_address": PINNED}],
        )

        assert response.status_code == 403, response.text

    def test_consumer_may_let_neutron_allocate(self, apps, world):
        client = TestClient(apps["neutron"])

        response = create_port(
            client,
            world["headers"],
            network_id=world["network"].id,
            fixed_ips=[{"subnet_id": world["subnet"].id}],
        )

        assert response.status_code == 201, response.text

    def test_consumer_may_create_a_port_with_no_fixed_ips(self, apps, world):
        client = TestClient(apps["neutron"])

        response = create_port(client, world["headers"], network_id=world["network"].id)

        assert response.status_code == 201, response.text

    def test_admin_may_pin_an_ip_for_the_consumer(self, apps, world):
        client = TestClient(apps["neutron"])

        response = create_port(
            client,
            world["admin"],
            network_id=world["network"].id,
            project_id=world["consumer_id"],
            fixed_ips=[{"subnet_id": world["subnet"].id, "ip_address": PINNED}],
        )

        assert response.status_code == 201, response.text
        assert response.json()["port"]["fixed_ips"][0]["ip_address"] == PINNED

    def test_a_tenant_may_pin_an_ip_on_its_own_network(self, apps, world):
        """The rule is about ownership, not about pinning."""
        client = TestClient(apps["neutron"])
        own = db.create_network(name="own-net", project_id=world["consumer_id"])
        own_subnet = db.create_subnet(
            network_id=own.id, cidr="10.91.0.0/24", project_id=world["consumer_id"]
        )

        response = create_port(
            client,
            world["headers"],
            network_id=own.id,
            fixed_ips=[{"subnet_id": own_subnet.id, "ip_address": "10.91.0.50"}],
        )

        assert response.status_code == 201, response.text


class TestRevokingTheShare:
    def test_policy_cannot_be_deleted_while_the_consumer_holds_a_port(self, apps, world):
        client = TestClient(apps["neutron"])
        create_port(client, world["headers"], network_id=world["network"].id)
        policy = db.list_rbac_policies()[0]

        response = client.delete(f"/v2.0/rbac-policies/{policy.id}", headers=world["admin"])

        assert response.status_code == 409, response.text

    def test_policy_can_be_deleted_once_the_ports_are_gone(self, apps, world):
        client = TestClient(apps["neutron"])
        port_id = create_port(client, world["headers"], network_id=world["network"].id).json()[
            "port"
        ]["id"]
        client.delete(f"/v2.0/ports/{port_id}", headers=world["headers"])
        policy = db.list_rbac_policies()[0]

        response = client.delete(f"/v2.0/rbac-policies/{policy.id}", headers=world["admin"])

        assert response.status_code == 204, response.text
