"""Test Nova extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.exceptions import PortInUseError
from tests.conftest import grant_scope

# Create Nova app for testing
service_apps = create_all_service_apps()
nova_app = service_apps["nova"]
client = TestClient(nova_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._servers.clear()
    db._tokens.clear()
    db._keypairs.clear()
    db._server_volume_attachments.clear()
    db._server_network_interfaces.clear()
    db._server_consoles.clear()
    db._server_tags.clear()
    db._init_default_flavors()
    db._init_default_images()
    db._init_nova_extensions()
    db.reset_keystone()
    yield


@pytest.fixture
def auth_token():
    """Get a valid auth token for testing."""
    # Use the keystone app to get a proper token
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


@pytest.fixture
def test_server(auth_token):
    """Create a test server."""
    response = client.post(
        "/v2.1/servers",
        json={
            "server": {
                "name": "test-server",
                "flavorRef": "1",
                "imageRef": None,
            }
        },
        headers={"X-Auth-Token": auth_token},
    )
    assert response.status_code == 202
    return response.json()["server"]["id"]


class TestNovaExtensions:
    """Test Nova extensions endpoints."""

    def test_list_extensions(self, auth_token):
        """Test listing Nova extensions."""
        response = client.get("/v2.1/extensions", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "extensions" in data
        assert len(data["extensions"]) > 0

        # Check for specific extensions
        extension_aliases = [ext["alias"] for ext in data["extensions"]]
        assert "os-volume_attachments" in extension_aliases
        assert "os-interface" in extension_aliases
        assert "os-consoles" in extension_aliases
        assert "os-server-tags" in extension_aliases

    def test_get_extension(self, auth_token):
        """Test getting a specific extension."""
        response = client.get(
            "/v2.1/extensions/os-volume_attachments", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "extension" in data
        assert data["extension"]["alias"] == "os-volume_attachments"
        assert data["extension"]["name"] == "VolumeAttachments"

    def test_get_extension_not_found(self, auth_token):
        """Test getting a non-existent extension."""
        response = client.get("/v2.1/extensions/nonexistent", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 404


class TestServerVolumeAttachments:
    """Test server volume attachment endpoints."""

    def test_list_volume_attachments_empty(self, auth_token, test_server):
        """Test listing volume attachments for a server with none attached."""
        response = client.get(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "volumeAttachments" in data
        assert data["volumeAttachments"] == []

    def test_attach_volume_to_server(self, auth_token, test_server):
        """Test attaching a volume to a server."""
        # First create a volume using Cinder API
        cinder_app = create_all_service_apps()["cinder"]
        cinder_client = TestClient(cinder_app)

        volume_response = cinder_client.post(
            "/v3/admin/volumes",  # Use admin project since our token is for admin
            json={
                "volume": {
                    "name": "test-volume",
                    "size": 1,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert volume_response.status_code == 202
        volume_id = volume_response.json()["volume"]["id"]

        # Now attach it to the server
        response = client.post(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            json={
                "volumeAttachment": {
                    "volumeId": volume_id,
                    "device": "/dev/vdb",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "volumeAttachment" in data
        assert data["volumeAttachment"]["volumeId"] == volume_id
        assert data["volumeAttachment"]["serverId"] == test_server
        assert data["volumeAttachment"]["device"] == "/dev/vdb"

    def test_list_volume_attachments_after_attach(self, auth_token, test_server):
        """Test listing volume attachments after attaching a volume."""
        # Create and attach a volume using Cinder API
        cinder_app = create_all_service_apps()["cinder"]
        cinder_client = TestClient(cinder_app)

        volume_response = cinder_client.post(
            "/v3/admin/volumes",
            json={"volume": {"name": "test-volume", "size": 1}},
            headers={"X-Auth-Token": auth_token},
        )
        volume_id = volume_response.json()["volume"]["id"]

        client.post(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            json={"volumeAttachment": {"volumeId": volume_id}},
            headers={"X-Auth-Token": auth_token},
        )

        # List attachments
        response = client.get(
            f"/v2.1/servers/{test_server}/os-volume_attachments",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["volumeAttachments"]) == 1
        assert data["volumeAttachments"][0]["volumeId"] == volume_id


class TestServerNetworkInterfaces:
    """Test server network interface endpoints."""

    def test_list_interfaces_empty(self, auth_token, test_server):
        """Test listing interfaces for a server with none attached."""
        response = client.get(
            f"/v2.1/servers/{test_server}/os-interface",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "interfaceAttachments" in data
        assert data["interfaceAttachments"] == []

    def test_attach_interface_to_server(self, auth_token, test_server):
        """Test attaching a network interface to a server by network."""
        network = db.create_network(name="attach-test-net", project_id="admin")
        subnet = db.create_subnet(network_id=network.id, cidr="192.168.1.0/24", project_id="admin")

        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={
                "interfaceAttachment": {
                    "net_id": network.id,
                    "fixed_ip": "192.168.1.100",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "interfaceAttachment" in data
        assert data["interfaceAttachment"]["net_id"] == network.id
        assert "port_id" in data["interfaceAttachment"]
        assert "mac_addr" in data["interfaceAttachment"]
        # subnet_id is resolved from the subnet CIDR containing the fixed IP.
        assert data["interfaceAttachment"]["fixed_ips"][0]["subnet_id"] == subnet.id

        # The interface is backed by a real port bound to the server.
        port = db.get_port(data["interfaceAttachment"]["port_id"])
        assert port is not None
        assert port.device_id == test_server
        assert port.device_owner == "compute:nova"

    def test_attach_interface_unknown_network_returns_404(self, auth_token, test_server):
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": "no-such-network"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404
        assert "could not be found" in response.json()["error"]["message"]

    def test_attach_interface_rejects_both_net_and_port(self, auth_token, test_server):
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": "n", "port_id": "p"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 400

    def test_attach_interface_rejects_fixed_ip_without_network(self, auth_token, test_server):
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"fixed_ip": "192.168.1.10"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 400


class TestInterfaceAttachPortOwnership:
    """Port project ownership semantics of interface attach.

    Mirrors real Nova/Neutron: a port created by an admin token without an
    explicit tenant_id is owned by the admin project, so a tenant-scoped
    attach cannot see it and gets 404 — while the same port created with the
    tenant's project id attaches fine.
    """

    def _make_tenant(self, admin_token, name):
        """Create a project and return (scoped_token, project_id)."""
        keystone_client = TestClient(create_all_service_apps()["keystone"])
        project_response = keystone_client.post(
            "/v3/projects",
            json={"project": {"name": name, "domain_id": "default"}},
            headers={"X-Auth-Token": admin_token},
        )
        project_id = project_response.json()["project"]["id"]
        # Scoping needs a real assignment, as it does against a real Keystone.
        grant_scope(project_id=project_id)
        token_response = keystone_client.post(
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
                    "scope": {"project": {"name": name, "domain": {"id": "default"}}},
                }
            },
        )
        return token_response.headers["X-Subject-Token"], project_id

    def _make_tenant_server(self, tenant_token):
        response = client.post(
            "/v2.1/servers",
            json={"server": {"name": "tenant-vm", "flavorRef": "1", "imageRef": None}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert response.status_code == 202
        return response.json()["server"]["id"]

    def _admin_create_port(self, admin_token, network_id, tenant_id=None):
        neutron_client = TestClient(create_all_service_apps()["neutron"])
        payload = {"port": {"network_id": network_id}}
        if tenant_id:
            payload["port"]["tenant_id"] = tenant_id
        response = neutron_client.post(
            "/v2.0/ports", json=payload, headers={"X-Auth-Token": admin_token}
        )
        assert response.status_code in (200, 201), response.text
        return response.json()["port"]

    def test_admin_port_without_tenant_id_is_invisible_to_tenant_attach(self, auth_token):
        tenant_token, tenant_project_id = self._make_tenant(auth_token, "port-owner-test-a")
        server_id = self._make_tenant_server(tenant_token)
        network = db.create_network(name="tenant-net", project_id=tenant_project_id)
        db.create_subnet(network_id=network.id, cidr="10.1.0.0/24", project_id=tenant_project_id)

        # Admin omits tenant_id: Neutron places the port in the admin project.
        port = self._admin_create_port(auth_token, network.id)

        response = client.post(
            f"/v2.1/servers/{server_id}/os-interface",
            json={"interfaceAttachment": {"port_id": port["id"]}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert response.status_code == 404
        assert response.json()["error"]["message"] == f"Port id {port['id']} could not be found."

    def test_admin_port_with_tenant_id_attaches_for_tenant(self, auth_token):
        tenant_token, tenant_project_id = self._make_tenant(auth_token, "port-owner-test-b")
        server_id = self._make_tenant_server(tenant_token)
        network = db.create_network(name="tenant-net-b", project_id=tenant_project_id)
        db.create_subnet(network_id=network.id, cidr="10.2.0.0/24", project_id=tenant_project_id)

        port = self._admin_create_port(auth_token, network.id, tenant_id=tenant_project_id)

        response = client.post(
            f"/v2.1/servers/{server_id}/os-interface",
            json={"interfaceAttachment": {"port_id": port["id"]}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert response.status_code == 200, response.text
        attachment = response.json()["interfaceAttachment"]
        assert attachment["port_id"] == port["id"]
        assert attachment["mac_addr"] == port["mac_address"]

        bound_port = db.get_port(port["id"])
        assert bound_port is not None
        assert bound_port.device_id == server_id
        assert bound_port.device_owner == "compute:nova"

    def test_attach_port_already_in_use_returns_409(self, auth_token):
        tenant_token, tenant_project_id = self._make_tenant(auth_token, "port-owner-test-c")
        server_id = self._make_tenant_server(tenant_token)
        other_server_id = self._make_tenant_server(tenant_token)
        network = db.create_network(name="tenant-net-c", project_id=tenant_project_id)
        db.create_subnet(network_id=network.id, cidr="10.3.0.0/24", project_id=tenant_project_id)
        port = self._admin_create_port(auth_token, network.id, tenant_id=tenant_project_id)

        first = client.post(
            f"/v2.1/servers/{server_id}/os-interface",
            json={"interfaceAttachment": {"port_id": port["id"]}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert first.status_code == 200

        second = client.post(
            f"/v2.1/servers/{other_server_id}/os-interface",
            json={"interfaceAttachment": {"port_id": port["id"]}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert second.status_code == 409
        assert second.json()["error"]["message"] == f"Port {port['id']} is still in use."

    def test_detach_unbinds_port(self, auth_token):
        tenant_token, tenant_project_id = self._make_tenant(auth_token, "port-owner-test-d")
        server_id = self._make_tenant_server(tenant_token)
        network = db.create_network(name="tenant-net-d", project_id=tenant_project_id)
        db.create_subnet(network_id=network.id, cidr="10.4.0.0/24", project_id=tenant_project_id)
        port = self._admin_create_port(auth_token, network.id, tenant_id=tenant_project_id)

        attach = client.post(
            f"/v2.1/servers/{server_id}/os-interface",
            json={"interfaceAttachment": {"port_id": port["id"]}},
            headers={"X-Auth-Token": tenant_token},
        )
        assert attach.status_code == 200

        detach = client.delete(
            f"/v2.1/servers/{server_id}/os-interface/{port['id']}",
            headers={"X-Auth-Token": tenant_token},
        )
        assert detach.status_code == 202

        unbound_port = db.get_port(port["id"])
        assert unbound_port is not None
        assert unbound_port.device_id == ""
        assert unbound_port.device_owner == ""


class TestInterfaceFixedIPValidation:
    """fixed_ip validation on attach-by-network, mirroring real Nova.

    Real Nova maps Neutron's InvalidIpForNetwork to 400 InvalidInput and
    IpAddressInUse/IpAddressAlreadyAllocated to 409 FixedIpAlreadyInUse.
    """

    def _make_net(self, cidr="10.20.0.0/24"):
        network = db.create_network(name="fixed-ip-net", project_id="admin")
        subnet = db.create_subnet(network_id=network.id, cidr=cidr, project_id="admin")
        return network, subnet

    def test_attach_out_of_cidr_fixed_ip_returns_400(self, auth_token, test_server):
        network, _ = self._make_net()
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": network.id, "fixed_ip": "10.99.0.5"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 400
        assert response.json()["error"]["message"] == (
            f"Fixed IP 10.99.0.5 is not a valid ip address for network {network.id}."
        )

    def test_attach_malformed_fixed_ip_returns_400(self, auth_token, test_server):
        network, _ = self._make_net()
        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": network.id, "fixed_ip": "not-an-ip"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 400

    def test_attach_duplicate_fixed_ip_returns_409(self, auth_token, test_server):
        network, subnet = self._make_net()
        db.create_port(
            network_id=network.id,
            project_id="admin",
            fixed_ips=[{"subnet_id": subnet.id, "ip_address": "10.20.0.9"}],
        )

        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": network.id, "fixed_ip": "10.20.0.9"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 409
        assert response.json()["error"]["message"] == "Fixed IP 10.20.0.9 is already in use."

    def test_attach_resolves_subnet_by_cidr(self, auth_token, test_server):
        """With several subnets, the fixed IP lands in the one containing it."""
        network = db.create_network(name="two-subnet-net", project_id="admin")
        db.create_subnet(network_id=network.id, cidr="10.30.0.0/24", project_id="admin")
        second = db.create_subnet(network_id=network.id, cidr="10.31.0.0/24", project_id="admin")

        response = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"net_id": network.id, "fixed_ip": "10.31.0.7"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["interfaceAttachment"]["fixed_ips"][0]["subnet_id"] == second.id


class TestInterfacePortLifecycle:
    """Port lifecycle on detach and server delete, mirroring real Nova.

    Nova's deallocate_port_for_instance deletes ports Nova created for the
    attach and only unbinds pre-existing ones; instance delete does the same.
    """

    def _attach_by_network(self, auth_token, server_id):
        network = db.create_network(name="lifecycle-net", project_id="admin")
        db.create_subnet(network_id=network.id, cidr="10.40.0.0/24", project_id="admin")
        response = client.post(
            f"/v2.1/servers/{server_id}/os-interface",
            json={"interfaceAttachment": {"net_id": network.id, "fixed_ip": "10.40.0.5"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        return network, response.json()["interfaceAttachment"]["port_id"]

    def test_detach_deletes_nova_created_port(self, auth_token, test_server):
        _, port_id = self._attach_by_network(auth_token, test_server)

        detach = client.delete(
            f"/v2.1/servers/{test_server}/os-interface/{port_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert detach.status_code == 202
        assert db.get_port(port_id) is None

    def test_db_attach_rejects_in_use_port(self, test_server):
        """The in-use guard holds even when the API layer is bypassed."""
        network = db.create_network(name="guard-net", project_id="admin")
        db.create_subnet(network_id=network.id, cidr="10.41.0.0/24", project_id="admin")
        port = db.create_port(network_id=network.id, project_id="admin")
        assert port is not None
        port.device_id = "some-other-server"

        with pytest.raises(PortInUseError):
            db.attach_interface_to_server(server_id=test_server, port=port)

    def test_delete_server_releases_ports(self, auth_token, test_server):
        network, nova_port_id = self._attach_by_network(auth_token, test_server)
        preexisting = db.create_port(
            network_id=network.id,
            project_id="admin",
            fixed_ips=[{"subnet_id": "", "ip_address": "10.40.0.20"}],
        )
        assert preexisting is not None
        attach = client.post(
            f"/v2.1/servers/{test_server}/os-interface",
            json={"interfaceAttachment": {"port_id": preexisting.id}},
            headers={"X-Auth-Token": auth_token},
        )
        assert attach.status_code == 200

        delete = client.delete(
            f"/v2.1/servers/{test_server}",
            headers={"X-Auth-Token": auth_token},
        )
        assert delete.status_code == 204

        # Nova-created port is gone, pre-existing port survives unbound.
        assert db.get_port(nova_port_id) is None
        survivor = db.get_port(preexisting.id)
        assert survivor is not None
        assert survivor.device_id == ""
        assert survivor.device_owner == ""
        assert db.list_server_network_interfaces(test_server) == []


class TestServerDiagnostics:
    """Test server diagnostics endpoint."""

    def test_get_server_diagnostics(self, auth_token, test_server):
        """Test getting server diagnostics."""
        response = client.get(
            f"/v2.1/servers/{test_server}/diagnostics",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "state" in data
        assert "driver" in data
        assert "hypervisor" in data
        assert "uptime" in data
        assert "num_cpus" in data
        assert "memory" in data


class TestServerConsoles:
    """Test server console endpoints."""

    def test_list_consoles_empty(self, auth_token, test_server):
        """Test listing consoles for a server with none created."""
        response = client.get(
            f"/v2.1/servers/{test_server}/consoles",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "consoles" in data
        assert data["consoles"] == []

    def test_create_console(self, auth_token, test_server):
        """Test creating a console for a server."""
        response = client.post(
            f"/v2.1/servers/{test_server}/consoles",
            json={"console": {"type": "novnc"}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "console" in data
        assert data["console"]["console_type"] == "novnc"
        assert "id" in data["console"]

    def test_create_remote_console(self, auth_token, test_server):
        """Test creating a remote console for a server."""
        response = client.post(
            f"/v2.1/servers/{test_server}/remote-consoles",
            json={
                "remote_console": {
                    "type": "novnc",
                    "protocol": "vnc",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "remote_console" in data
        assert data["remote_console"]["type"] == "novnc"
        assert data["remote_console"]["protocol"] == "vnc"
        assert "url" in data["remote_console"]


class TestServerTags:
    """Test server tags endpoints."""

    def test_list_tags_empty(self, auth_token, test_server):
        """Test listing tags for a server with none set."""
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "tags" in data
        assert data["tags"] == []

    def test_add_server_tag(self, auth_token, test_server):
        """Test adding a tag to a server."""
        response = client.put(
            f"/v2.1/servers/{test_server}/tags/production",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        # Verify tag was added
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert "production" in response.json()["tags"]

    def test_replace_server_tags(self, auth_token, test_server):
        """Test replacing all tags on a server."""
        response = client.put(
            f"/v2.1/servers/{test_server}/tags",
            json={"tags": ["web", "production", "database"]},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert set(data["tags"]) == {"web", "production", "database"}

    def test_check_server_tag(self, auth_token, test_server):
        """Test checking if a server has a specific tag."""
        # Add a tag first
        client.put(
            f"/v2.1/servers/{test_server}/tags/test",
            headers={"X-Auth-Token": auth_token},
        )

        # Check tag exists
        response = client.get(
            f"/v2.1/servers/{test_server}/tags/test",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Check non-existent tag
        response = client.get(
            f"/v2.1/servers/{test_server}/tags/nonexistent",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_remove_server_tag(self, auth_token, test_server):
        """Test removing a tag from a server."""
        # Add a tag first
        client.put(
            f"/v2.1/servers/{test_server}/tags/temp",
            headers={"X-Auth-Token": auth_token},
        )

        # Remove the tag
        response = client.delete(
            f"/v2.1/servers/{test_server}/tags/temp",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify tag was removed
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert "temp" not in response.json()["tags"]

    def test_clear_server_tags(self, auth_token, test_server):
        """Test clearing all tags from a server."""
        # Add some tags first
        client.put(
            f"/v2.1/servers/{test_server}/tags",
            json={"tags": ["tag1", "tag2", "tag3"]},
            headers={"X-Auth-Token": auth_token},
        )

        # Clear all tags
        response = client.delete(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify tags are cleared
        response = client.get(
            f"/v2.1/servers/{test_server}/tags",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        assert response.json()["tags"] == []


class TestTenantIsolation:
    """Test tenant isolation for new endpoints."""

    def test_volume_attachment_tenant_isolation(self, auth_token):
        """Test that users cannot attach volumes to other tenants' servers."""
        # Create server and volume in different projects
        server_response = client.post(
            "/v2.1/servers",
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": None,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        server_id = server_response.json()["server"]["id"]

        # Create a different project and get token
        keystone_app = create_all_service_apps()["keystone"]
        keystone_client = TestClient(keystone_app)

        # Create a new project for isolation testing
        _project_response = keystone_client.post(
            "/v3/projects",
            json={
                "project": {
                    "name": "other-project",
                    "domain_id": "default",
                    "description": "Test project for isolation",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )

        # Get token scoped to the other project
        grant_scope(project_name="other-project")
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
                    "scope": {"project": {"name": "other-project", "domain": {"id": "default"}}},
                }
            },
        )
        other_token = other_token_response.headers["X-Subject-Token"]

        # Try to access volume attachments with wrong token
        response = client.get(
            f"/v2.1/servers/{server_id}/os-volume_attachments",
            headers={"X-Auth-Token": other_token},
        )
        assert response.status_code == 404  # Server not found due to tenant isolation

    def test_interface_attachment_tenant_isolation(self, auth_token):
        """Test that users cannot manage interfaces on other tenants' servers."""
        # Create server
        server_response = client.post(
            "/v2.1/servers",
            json={
                "server": {
                    "name": "test-server",
                    "flavorRef": "1",
                    "imageRef": None,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        server_id = server_response.json()["server"]["id"]

        # Create a different project and get token
        keystone_app = create_all_service_apps()["keystone"]
        keystone_client = TestClient(keystone_app)

        # Create a new project for isolation testing
        _project_response = keystone_client.post(
            "/v3/projects",
            json={
                "project": {
                    "name": "interface-test-project",
                    "domain_id": "default",
                    "description": "Test project for interface isolation",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )

        # Get token scoped to the other project
        grant_scope(project_name="interface-test-project")
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
                    "scope": {
                        "project": {"name": "interface-test-project", "domain": {"id": "default"}}
                    },
                }
            },
        )
        other_token = other_token_response.headers["X-Subject-Token"]

        # Try to access interfaces with wrong token
        response = client.get(
            f"/v2.1/servers/{server_id}/os-interface",
            headers={"X-Auth-Token": other_token},
        )
        assert response.status_code == 404  # Server not found due to tenant isolation
