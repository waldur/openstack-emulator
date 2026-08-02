"""The service catalog must name the ports the services are bound to.

``--port-offset`` shifts every listener, but the catalog used to hardcode the
standard ports. Clients resolve every endpoint through the catalog, so an
offset run handed out a catalog pointing at ports nothing was serving and any
SDK call after authentication dialled a closed port. The listeners and the
catalog have to agree.
"""

import pytest

from emulator.api.unified_app import SERVICE_PORTS
from emulator.core.database import Database

# Catalog service type -> the SERVICE_PORTS key serving it.
SERVICE_TYPE_PORTS = {
    "identity": "keystone",
    "compute": "nova",
    "volumev3": "cinder",
    "image": "glance",
    "network": "neutron",
    "object-store": "swift",
    "rating": "cloudkitty",
    "placement": "placement",
    "load-balancer": "octavia",
}


def catalog_ports(db: Database) -> dict[str, set[int]]:
    """Every port the catalog advertises, keyed by service type."""
    catalog = db._generate_service_catalog("http://localhost:5000/v3", "project-1")
    ports = {}
    for entry in catalog:
        found = set()
        for endpoint in entry["endpoints"]:
            _, _, rest = endpoint["url"].partition("://")
            host_port = rest.split("/")[0]
            found.add(int(host_port.split(":")[1]))
        ports[entry["type"]] = found
    return ports


class TestDefaultPorts:
    def test_catalog_uses_standard_ports_when_unshifted(self):
        ports = catalog_ports(Database())

        for service_type, port_key in SERVICE_TYPE_PORTS.items():
            if service_type in ports:
                assert ports[service_type] == {SERVICE_PORTS[port_key]}, service_type


class TestOffsetPorts:
    @pytest.mark.parametrize("offset", [100, 1000])
    def test_every_catalog_port_is_shifted(self, offset):
        db = Database()
        db.port_offset = offset

        ports = catalog_ports(db)

        for service_type, port_key in SERVICE_TYPE_PORTS.items():
            if service_type in ports:
                expected = SERVICE_PORTS[port_key] + offset
                assert ports[service_type] == {expected}, service_type

    def test_no_catalog_port_is_left_unshifted(self):
        """A missed service is the whole failure mode — catch it generically."""
        db = Database()
        db.port_offset = 100
        standard = set(SERVICE_PORTS.values())

        advertised = {port for ports in catalog_ports(db).values() for port in ports}

        assert not (advertised & standard), f"unshifted ports in catalog: {advertised & standard}"


class TestOffsetIsNotState:
    def test_offset_defaults_to_zero(self):
        assert Database().port_offset == 0


class TestStatusUiHonoursOffset:
    """The dashboard probes the ports the services are bound to.

    It health-checks by connecting to each service's port. Probing the standard
    ports under an offset made every service render OFFLINE while the emulator
    was serving happily one port-block over.
    """

    def test_reported_ports_are_shifted(self, monkeypatch):
        from emulator.api import status_ui

        db = Database()
        db.port_offset = 100
        monkeypatch.setattr(status_ui, "db", db)

        reported = {
            name: info["port"] + status_ui.db.port_offset
            for name, info in status_ui.SERVICES.items()
        }

        assert reported["keystone"] == SERVICE_PORTS["keystone"] + 100
        assert reported["nova"] == SERVICE_PORTS["nova"] + 100
        assert not set(reported.values()) & set(SERVICE_PORTS.values())
