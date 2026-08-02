"""A rejected token must answer 401, not a resource-shaped 404.

Real OpenStack puts keystonemiddleware in front of every service, so an expired
or unknown token is refused with 401 before the request reaches a resource
handler. Clients rely on that: keystoneauth1 re-authenticates and replays the
request on a 401, which is how a long-running session survives token expiry.

Neutron, Glance and Octavia used to swallow the rejection and fall back to the
literal project ``"admin"`` as a filter value. For a by-id lookup that turned an
expired token into "Port not found" — a 404 the client takes at face value and
never retries, so the caller sees a resource that plainly exists as missing.
"""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import scoped_token

BAD = {"X-Auth-Token": "expired-or-unknown-token"}


@pytest.fixture
def apps():
    return create_all_service_apps()


@pytest.fixture(autouse=True)
def reset_db():
    db.reset_keystone()
    db.reset_neutron()
    yield


@pytest.fixture
def admin_headers():
    return {"X-Auth-Token": scoped_token(project_name="admin", role_name="admin").id}


@pytest.fixture
def port(admin_headers):
    """A port that unambiguously exists, owned by a non-admin project."""
    project = db.create_project(name="tenant-a", domain_id="default")
    net = db.create_network(name="net-a", project_id=project.id)
    db.create_subnet(network_id=net.id, cidr="192.168.9.0/24", project_id=project.id)
    return db.create_port(network_id=net.id, project_id=project.id)


class TestRejectedToken:
    """The token is present and invalid — the answer is 401."""

    def test_neutron_get_port(self, apps, port):
        response = TestClient(apps["neutron"]).get(f"/v2.0/ports/{port.id}", headers=BAD)

        assert response.status_code == 401, response.text

    def test_neutron_list_ports(self, apps, port):
        assert TestClient(apps["neutron"]).get("/v2.0/ports", headers=BAD).status_code == 401

    def test_glance_create_image(self, apps):
        response = TestClient(apps["glance"]).post(
            "/v2/images", headers=BAD, json={"name": "img", "disk_format": "qcow2"}
        )

        assert response.status_code == 401, response.text

    def test_octavia_create_load_balancer(self, apps):
        response = TestClient(apps["octavia"]).post(
            "/v2/lbaas/loadbalancers", headers=BAD, json={"loadbalancer": {"name": "lb"}}
        )

        assert response.status_code == 401, response.text

    def test_nova_agrees(self, apps):
        """Nova already behaved this way; the others now match it."""
        assert TestClient(apps["nova"]).get("/v2.1/servers", headers=BAD).status_code == 401


class TestValidToken:
    """The fix must not cost cross-project admin access."""

    def test_admin_still_reads_another_projects_port(self, apps, port, admin_headers):
        response = TestClient(apps["neutron"]).get(f"/v2.0/ports/{port.id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["port"]["id"] == port.id


class TestNoToken:
    """Token-less requests keep the development fallback."""

    def test_neutron_list_ports_without_a_token(self, apps):
        assert TestClient(apps["neutron"]).get("/v2.0/ports").status_code == 200
