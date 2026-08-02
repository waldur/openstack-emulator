"""Tests for cross-project scoping of Nova server and Cinder volume listings.

Both services require ``all_tenants`` to cross a project boundary: a
``project_id`` filter on its own is ignored (Nova) or overridden (Cinder), even
for an admin. Verified against ``ServersController._get_servers`` in nova and
``API.get_all`` in cinder. Clients that pass only ``project_id`` — as the
openstacksdk ``servers(project_id=...)`` / ``volumes(project_id=...)`` calls do —
get their own resources back, and these tests pin that rather than papering
over it.
"""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import grant_scope

TENANT = "tenant-1"
OTHER = "tenant-2"


@pytest.fixture
def apps():
    """Build the service apps once per test."""
    return create_all_service_apps()


@pytest.fixture(autouse=True)
def reset_db():
    """Reset compute and storage state between tests."""
    db.reset_keystone()
    db.reset_cinder()
    db._servers.clear()
    yield


def _token(apps, project_name, project_id=None):
    keystone = TestClient(apps["keystone"])
    scope = {"project": {"id": project_id}} if project_id else {"project": {"name": project_name}}
    response = keystone.post(
        "/v3/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "admin" if project_name == "admin" else "member",
                            "domain": {"id": "default"},
                            "password": "s4l4dus",
                        }
                    },
                },
                "scope": scope,
            }
        },
    )
    return {"X-Auth-Token": response.headers["X-Subject-Token"]}


@pytest.fixture
def admin_headers(apps):
    """Headers for a token scoped to the admin project."""
    return _token(apps, "admin")


@pytest.fixture
def tenant_headers(apps):
    """Headers for an unprivileged token scoped to TENANT."""
    grant_scope(project_name="tenant-one", project_id=TENANT, user_name="member")
    return _token(apps, "tenant-one", project_id=TENANT)


@pytest.fixture
def servers():
    """One server in each of two projects."""
    db.create_server(name="mine", flavor_id="1", image_id="img", tenant_id=TENANT)
    db.create_server(name="theirs", flavor_id="1", image_id="img", tenant_id=OTHER)


class TestNovaServerScoping:
    """Only all_tenants widens a Nova server listing."""

    def _names(self, response):
        return sorted(s["name"] for s in response.json()["servers"])

    def test_project_id_filter_alone_does_not_cross_projects(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get(f"/v2.1/servers?project_id={TENANT}", headers=admin_headers)
        # Nova forces project_id to the caller's own project when all_tenants is
        # absent, and the admin project owns neither server.
        assert self._names(response) == []

    def test_tenant_id_filter_alone_does_not_cross_projects(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get(f"/v2.1/servers?tenant_id={OTHER}", headers=admin_headers)
        assert self._names(response) == []

    def test_all_tenants_lists_every_project(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get("/v2.1/servers?all_tenants=True", headers=admin_headers)
        assert self._names(response) == ["mine", "theirs"]

    def test_all_tenants_with_project_id_filters_to_that_project(
        self, apps, admin_headers, servers
    ):
        client = TestClient(apps["nova"])
        response = client.get(
            f"/v2.1/servers?all_tenants=True&project_id={TENANT}", headers=admin_headers
        )
        assert self._names(response) == ["mine"]

    def test_all_tenants_accepts_the_tenant_id_alias(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get(
            f"/v2.1/servers?all_tenants=True&tenant_id={OTHER}", headers=admin_headers
        )
        assert self._names(response) == ["theirs"]

    def test_detail_listing_uses_the_same_rules(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get(
            f"/v2.1/servers/detail?all_tenants=True&project_id={TENANT}", headers=admin_headers
        )
        assert self._names(response) == ["mine"]

    def test_bare_all_tenants_key_means_true(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get("/v2.1/servers?all_tenants", headers=admin_headers)
        assert self._names(response) == ["mine", "theirs"]

    def test_falsy_all_tenants_stays_scoped(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get("/v2.1/servers?all_tenants=0", headers=admin_headers)
        assert self._names(response) == []

    def test_non_admin_cannot_use_the_filter_to_escape(self, apps, tenant_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get(f"/v2.1/servers?project_id={OTHER}", headers=tenant_headers)
        assert self._names(response) == ["mine"]

    def test_non_admin_all_tenants_is_forbidden(self, apps, tenant_headers, servers):
        client = TestClient(apps["nova"])
        response = client.get("/v2.1/servers?all_tenants=True", headers=tenant_headers)
        # Nova guards all_tenants with an admin-only policy check.
        assert response.status_code == 403


class TestCinderVolumeScoping:
    """Cinder requires all_tenants; a project_id filter alone does not escape."""

    @pytest.fixture(autouse=True)
    def volumes(self):
        db.create_volume(name="mine", size=1, project_id=TENANT, user_id="u1")
        db.create_volume(name="theirs", size=1, project_id=OTHER, user_id="u2")

    def _names(self, response):
        return sorted(v["name"] for v in response.json()["volumes"])

    def test_project_id_filter_alone_does_not_cross_projects(self, apps, admin_headers):
        client = TestClient(apps["cinder"])
        response = client.get(f"/v3/{TENANT}/volumes?project_id={OTHER}", headers=admin_headers)
        # Scoped to the account in the URL, exactly as Cinder does.
        assert self._names(response) == ["mine"]

    def test_all_tenants_lists_every_project(self, apps, admin_headers):
        client = TestClient(apps["cinder"])
        response = client.get(f"/v3/{TENANT}/volumes?all_tenants=true", headers=admin_headers)
        assert self._names(response) == ["mine", "theirs"]

    def test_all_tenants_with_project_id_filters_to_that_project(self, apps, admin_headers):
        client = TestClient(apps["cinder"])
        response = client.get(
            f"/v3/{TENANT}/volumes?all_tenants=true&project_id={OTHER}", headers=admin_headers
        )
        assert self._names(response) == ["theirs"]

    def test_non_admin_all_tenants_stays_scoped(self, apps, tenant_headers):
        client = TestClient(apps["cinder"])
        response = client.get(f"/v3/{TENANT}/volumes?all_tenants=true", headers=tenant_headers)
        assert self._names(response) == ["mine"]


class TestNovaQuotaDetail:
    """The detailed quota set is derived from the quota model, not a fixed list."""

    def test_every_limit_key_is_reported_with_usage(self, apps, admin_headers):
        client = TestClient(apps["nova"])
        response = client.get(f"/v2.1/os-quota-sets/{TENANT}/detail", headers=admin_headers)
        assert response.status_code == 200

        quota_set = response.json()["quota_set"]
        assert quota_set["id"] == TENANT
        expected = set(db.get_nova_quota(TENANT).limits())
        assert set(quota_set) - {"id"} == expected
        for key, value in quota_set.items():
            if key == "id":
                continue
            assert set(value) == {"limit", "in_use", "reserved"}

    def test_usage_reflects_running_servers(self, apps, admin_headers, servers):
        client = TestClient(apps["nova"])
        quota_set = client.get(
            f"/v2.1/os-quota-sets/{TENANT}/detail", headers=admin_headers
        ).json()["quota_set"]
        assert quota_set["instances"]["in_use"] == 1


class TestNovaQuotaClassSets:
    """Quota classes hold the compute limits new projects inherit."""

    def test_defaults_then_update(self, apps, admin_headers):
        client = TestClient(apps["nova"])

        body = client.get("/v2.1/os-quota-class-sets/default", headers=admin_headers).json()
        assert body["quota_class_set"]["id"] == "default"
        assert body["quota_class_set"]["cores"] == 20

        client.put(
            "/v2.1/os-quota-class-sets/default",
            headers=admin_headers,
            json={"quota_class_set": {"cores": 64}},
        )
        body = client.get("/v2.1/os-quota-class-sets/default", headers=admin_headers).json()
        assert body["quota_class_set"]["cores"] == 64
