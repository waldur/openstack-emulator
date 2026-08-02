"""Tests for Nova binding ports when a server is booted.

Booting a server with a network request has to allocate and stamp a port, the
way ``allocate_for_instance`` does in nova/network/neutron.py:

    zone = 'compute:%s' % instance.availability_zone
    port_req_body = {'port': {'device_id': instance.uuid,
                              'device_owner': zone}}

Without that, a port exists but nothing links it to the server: a client that
follows an instance's ports by ``device_id`` — which is how Nova itself finds
them — sees nothing, and ``os-interface`` is empty while ``addresses`` claims
the server is on the network.
"""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import scoped_token

PROJECT = "port-binding-project"


@pytest.fixture
def apps():
    """Build the service apps once per test."""
    return create_all_service_apps()


@pytest.fixture(autouse=True)
def reset_db():
    """Reset compute, network and identity state between tests."""
    db.reset_keystone()
    db.reset_neutron()
    db._servers.clear()
    db._server_network_interfaces.clear()
    yield


@pytest.fixture
def headers():
    """An admin-scoped token."""
    token = scoped_token(project_name="admin", role_name="admin")
    return {"X-Auth-Token": token.id}


@pytest.fixture
def project_id(headers):
    """The project the token is scoped to."""
    return db.validate_token(headers["X-Auth-Token"]).project_id


@pytest.fixture
def image_id():
    """A seeded Glance image, since server create validates the reference."""
    return next(iter(db.list_glance_images())).id


@pytest.fixture
def network(project_id):
    """A network with one subnet."""
    net = db.create_network(name="net-a", project_id=project_id)
    db.create_subnet(network_id=net.id, cidr="192.168.5.0/24", project_id=project_id)
    return net


def _boot(client, headers, image_id, networks, availability_zone=None):
    body = {
        "server": {
            "name": "vm",
            "flavorRef": "1",
            "imageRef": image_id,
            "networks": networks,
        }
    }
    if availability_zone:
        body["server"]["availability_zone"] = availability_zone
    return client.post("/v2.1/servers", headers=headers, json=body)


class TestBootWithExistingPort:
    """A port named in the request is bound to the new server."""

    def test_port_is_stamped_with_the_server(self, apps, headers, image_id, network, project_id):
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])

        response = _boot(client, headers, image_id, [{"port": port.id}])
        assert response.status_code == 202, response.text
        server_id = response.json()["server"]["id"]

        bound = db.get_port(port.id)
        assert bound.device_id == server_id
        assert bound.device_owner == "compute:nova"

    def test_device_owner_follows_the_availability_zone(
        self, apps, headers, image_id, network, project_id
    ):
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])

        _boot(client, headers, image_id, [{"port": port.id}], availability_zone="az-2")

        assert db.get_port(port.id).device_owner == "compute:az-2"

    def test_the_port_is_findable_by_device_id(self, apps, headers, image_id, network, project_id):
        """This is the lookup Nova and its clients actually use."""
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])
        server_id = _boot(client, headers, image_id, [{"port": port.id}]).json()["server"]["id"]

        neutron = TestClient(apps["neutron"])
        found = neutron.get(f"/v2.0/ports?device_id={server_id}", headers=headers).json()

        assert [p["id"] for p in found["ports"]] == [port.id]

    def test_os_interface_reports_the_port(self, apps, headers, image_id, network, project_id):
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])
        server_id = _boot(client, headers, image_id, [{"port": port.id}]).json()["server"]["id"]

        interfaces = client.get(f"/v2.1/servers/{server_id}/os-interface", headers=headers).json()[
            "interfaceAttachments"
        ]

        assert [i["port_id"] for i in interfaces] == [port.id]

    def test_addresses_report_the_real_fixed_ip(self, apps, headers, image_id, network, project_id):
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])

        server = _boot(client, headers, image_id, [{"port": port.id}]).json()["server"]
        detail = client.get(f"/v2.1/servers/{server['id']}", headers=headers).json()["server"]

        # Keyed by network name, as Nova does, and carrying the port's own IP
        # rather than an invented one.
        assert "net-a" in detail["addresses"]
        assert detail["addresses"]["net-a"][0]["addr"] == port.fixed_ips[0].ip_address


class TestBootWithNetwork:
    """A network named in the request has Nova create the port."""

    def test_a_port_is_created_and_bound(self, apps, headers, image_id, network):
        client = TestClient(apps["nova"])

        server_id = _boot(client, headers, image_id, [{"uuid": network.id}]).json()["server"]["id"]

        ports = [p for p in db.list_ports() if p.device_id == server_id]
        assert len(ports) == 1
        assert ports[0].network_id == network.id
        assert ports[0].device_owner == "compute:nova"

    def test_a_nova_created_port_is_deleted_with_the_server(self, apps, headers, image_id, network):
        """Nova owns the ports it created, so they go away with the instance."""
        client = TestClient(apps["nova"])
        server_id = _boot(client, headers, image_id, [{"uuid": network.id}]).json()["server"]["id"]
        created = [p.id for p in db.list_ports() if p.device_id == server_id]

        client.delete(f"/v2.1/servers/{server_id}", headers=headers)

        assert db.get_port(created[0]) is None

    def test_a_pre_existing_port_is_only_unbound(
        self, apps, headers, image_id, network, project_id
    ):
        """A port the caller created outlives the instance, released not deleted."""
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])
        server_id = _boot(client, headers, image_id, [{"port": port.id}]).json()["server"]["id"]

        client.delete(f"/v2.1/servers/{server_id}", headers=headers)

        survivor = db.get_port(port.id)
        assert survivor is not None
        assert survivor.device_id == ""


class TestBootFailures:
    """A request naming something unusable is rejected, not silently ignored."""

    def test_unknown_port_is_rejected(self, apps, headers, image_id, network):
        client = TestClient(apps["nova"])

        response = _boot(client, headers, image_id, [{"port": "no-such-port"}])

        assert response.status_code == 400
        assert "no-such-port" in response.json()["error"]["message"]

    def test_unknown_network_is_rejected(self, apps, headers, image_id):
        client = TestClient(apps["nova"])

        response = _boot(client, headers, image_id, [{"uuid": "no-such-network"}])

        assert response.status_code == 400

    def test_a_port_already_in_use_is_rejected(self, apps, headers, image_id, network, project_id):
        port = db.create_port(network_id=network.id, project_id=project_id)
        client = TestClient(apps["nova"])
        _boot(client, headers, image_id, [{"port": port.id}])

        response = _boot(client, headers, image_id, [{"port": port.id}])

        assert response.status_code == 400
        assert "still in use" in response.json()["error"]["message"]

    def test_a_rejected_boot_leaves_no_server_behind(self, apps, headers, image_id, network):
        client = TestClient(apps["nova"])
        before = len(db.list_servers())

        _boot(client, headers, image_id, [{"port": "no-such-port"}])

        assert len(db.list_servers()) == before


class TestNoNetworkRequest:
    """Booting without a network request keeps its previous behaviour."""

    def test_addresses_are_still_populated(self, apps, headers, image_id):
        client = TestClient(apps["nova"])

        response = client.post(
            "/v2.1/servers",
            headers=headers,
            json={"server": {"name": "vm", "flavorRef": "1", "imageRef": image_id}},
        )

        assert response.status_code == 202
        detail = client.get(
            f"/v2.1/servers/{response.json()['server']['id']}", headers=headers
        ).json()["server"]
        assert detail["addresses"]
