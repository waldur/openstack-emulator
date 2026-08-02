"""Tests for the CloudKitty rating API."""

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


@pytest.fixture
def client(apps):
    """CloudKitty test client."""
    return TestClient(apps["cloudkitty"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset compute, storage and identity state between tests."""
    db.reset_keystone()
    db.reset_cinder()
    db._servers.clear()
    yield


def _token(apps, user_name, project_name=None, project_id=None):
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
                            "name": user_name,
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
    """Headers for a privileged token."""
    return _token(apps, "admin", project_name="admin")


@pytest.fixture
def tenant_headers(apps):
    """Headers for an unprivileged token scoped to TENANT."""
    grant_scope(project_name="tenant-one", project_id=TENANT, user_name="member")
    return _token(apps, "member", project_id=TENANT)


@pytest.fixture
def resources():
    """Two instances in one project and one volume in another."""
    db.create_server(name="a", flavor_id="1", image_id="img", tenant_id=TENANT)
    db.create_server(name="b", flavor_id="2", image_id="img", tenant_id=TENANT)
    db.create_volume(name="v", size=10, project_id=OTHER, user_id="u")


class TestSummary:
    """The v2 summary endpoint."""

    def test_table_format_is_the_default(self, client, admin_headers, resources):
        response = client.get("/v2/summary", headers=admin_headers)
        assert response.status_code == 200

        body = response.json()
        assert body["format"] == "table"
        assert body["total"] == 1
        assert body["columns"] == ["begin", "end", "qty", "rate"]
        # Two instances at 0.05 plus 10 GB at 0.01.
        row = dict(zip(body["columns"], body["results"][0]))
        assert row["qty"] == pytest.approx(12.0)
        assert row["rate"] == pytest.approx(0.2)

    def test_object_format(self, client, admin_headers, resources):
        response = client.get("/v2/summary?response_format=object", headers=admin_headers)
        body = response.json()

        assert body["format"] == "object"
        assert body["results"][0]["qty"] == pytest.approx(12.0)

    def test_invalid_format_is_400(self, client, admin_headers):
        response = client.get("/v2/summary?response_format=yaml", headers=admin_headers)
        assert response.status_code == 400

    def test_groupby_project(self, client, admin_headers, resources):
        response = client.get("/v2/summary?groupby=project_id", headers=admin_headers)
        body = response.json()

        assert body["columns"] == ["begin", "end", "project_id", "qty", "rate"]
        rows = [dict(zip(body["columns"], row)) for row in body["results"]]
        by_project = {row["project_id"]: row for row in rows}
        assert by_project[TENANT]["qty"] == pytest.approx(2.0)
        assert by_project[OTHER]["qty"] == pytest.approx(10.0)

    def test_multiple_groupby_fields(self, client, admin_headers, resources):
        response = client.get("/v2/summary?groupby=project_id&groupby=type", headers=admin_headers)
        body = response.json()

        assert body["columns"] == ["begin", "end", "project_id", "type", "qty", "rate"]
        assert body["total"] == 2

    def test_groupby_flavor(self, client, admin_headers, resources):
        response = client.get("/v2/summary?groupby=flavor_name", headers=admin_headers)
        rows = [dict(zip(response.json()["columns"], r)) for r in response.json()["results"]]

        names = {row["flavor_name"] for row in rows}
        assert "m1.tiny" in names
        assert "m1.small" in names

    def test_filter_by_project(self, client, admin_headers, resources):
        response = client.get(
            f"/v2/summary?filters=project_id:{TENANT}&groupby=project_id", headers=admin_headers
        )
        rows = [dict(zip(response.json()["columns"], r)) for r in response.json()["results"]]

        assert [row["project_id"] for row in rows] == [TENANT]

    def test_filter_by_type(self, client, admin_headers, resources):
        response = client.get("/v2/summary?filters=type:instance", headers=admin_headers)
        row = dict(zip(response.json()["columns"], response.json()["results"][0]))

        assert row["qty"] == pytest.approx(2.0)

    def test_malformed_filter_is_400(self, client, admin_headers):
        response = client.get("/v2/summary?filters=nocolon", headers=admin_headers)
        assert response.status_code == 400

    def test_empty_result_has_no_columns(self, client, admin_headers):
        body = client.get("/v2/summary", headers=admin_headers).json()
        assert body == {"total": 0, "columns": [], "results": [], "format": "table"}

    def test_non_admin_only_sees_its_own_project(self, client, tenant_headers, resources):
        response = client.get(
            f"/v2/summary?filters=project_id:{OTHER}&groupby=project_id", headers=tenant_headers
        )
        rows = [dict(zip(response.json()["columns"], r)) for r in response.json()["results"]]

        # The requested filter is overridden by the caller's own scope.
        assert [row["project_id"] for row in rows] == [TENANT]

    def test_pagination(self, client, admin_headers, resources):
        body = client.get(
            "/v2/summary?groupby=project_id&limit=1&offset=1", headers=admin_headers
        ).json()

        assert body["total"] == 2
        assert len(body["results"]) == 1

    def test_unauthenticated_is_401(self, client):
        assert client.get("/v2/summary").status_code == 401


class TestDataframes:
    """The v2 dataframes endpoint."""

    def test_lists_points_grouped_by_scope(self, client, admin_headers, resources):
        body = client.get("/v2/dataframes", headers=admin_headers).json()

        assert body["total"] == 2
        scopes = {frame["tenant_id"] for frame in body["dataframes"]}
        assert scopes == {TENANT, OTHER}

    def test_resource_shape(self, client, admin_headers, resources):
        body = client.get(f"/v2/dataframes?filters=project_id:{OTHER}", headers=admin_headers)
        resource = body.json()["dataframes"][0]["resources"][0]

        assert resource["service"] == "volume.size"
        assert resource["volume"] == "10.0"
        assert resource["rating"] == {"price": "0.1"}

    def test_non_admin_is_scoped(self, client, tenant_headers, resources):
        body = client.get("/v2/dataframes", headers=tenant_headers).json()

        assert [frame["tenant_id"] for frame in body["dataframes"]] == [TENANT]


class TestRatingModules:
    """The v1 rating module listing."""

    def test_lists_modules(self, client, admin_headers):
        body = client.get("/v1/rating/modules", headers=admin_headers).json()

        modules = {m["module_id"]: m for m in body["modules"]}
        assert modules["hashmap"]["enabled"] is True
        assert modules["noop"]["enabled"] is False
