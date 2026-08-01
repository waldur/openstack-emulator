"""Tests for the Keystone project tags API and tag-based project filtering."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture
def client():
    """Create a test client."""
    apps = create_all_service_apps()
    return TestClient(apps["keystone"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset keystone state between tests."""
    db.reset_keystone()
    yield


@pytest.fixture
def auth_token(client):
    """Get an authentication token."""
    response = client.post(
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
def headers(auth_token):
    """Auth headers for API calls."""
    return {"X-Auth-Token": auth_token}


class TestProjectTagsOnProjectResource:
    """Tags round-trip through project create and update."""

    def test_create_with_tags(self, client, headers):
        response = client.post(
            "/v3/projects",
            headers=headers,
            json={"project": {"name": "tagged", "tags": ["waldur", "managed"]}},
        )
        assert response.status_code == 201
        assert response.json()["project"]["tags"] == ["waldur", "managed"]

    def test_patch_replaces_tags(self, client, headers):
        project = db.create_project(name="p1", domain_id="default", tags=["old"])

        response = client.patch(
            f"/v3/projects/{project.id}",
            headers=headers,
            json={"project": {"tags": ["deleted_on_waldur"]}},
        )
        assert response.status_code == 200
        assert response.json()["project"]["tags"] == ["deleted_on_waldur"]

    def test_patch_without_tags_leaves_them_alone(self, client, headers):
        project = db.create_project(name="p2", domain_id="default", tags=["keep"])

        response = client.patch(
            f"/v3/projects/{project.id}",
            headers=headers,
            json={"project": {"description": "new description"}},
        )
        assert response.status_code == 200
        assert response.json()["project"]["tags"] == ["keep"]

    def test_patch_deduplicates(self, client, headers):
        project = db.create_project(name="p3", domain_id="default")

        response = client.patch(
            f"/v3/projects/{project.id}",
            headers=headers,
            json={"project": {"tags": ["a", "b", "a"]}},
        )
        assert response.json()["project"]["tags"] == ["a", "b"]


class TestProjectTagsEndpoints:
    """The dedicated /tags sub-resource."""

    def test_list_tags(self, client, headers):
        project = db.create_project(name="p4", domain_id="default", tags=["x", "y"])

        response = client.get(f"/v3/projects/{project.id}/tags", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"tags": ["x", "y"]}

    def test_replace_all_tags(self, client, headers):
        project = db.create_project(name="p5", domain_id="default", tags=["x"])

        response = client.put(
            f"/v3/projects/{project.id}/tags", headers=headers, json={"tags": ["y", "z"]}
        )
        assert response.status_code == 200
        assert response.json() == {"tags": ["y", "z"]}

    def test_delete_all_tags(self, client, headers):
        project = db.create_project(name="p6", domain_id="default", tags=["x", "y"])

        response = client.delete(f"/v3/projects/{project.id}/tags", headers=headers)
        assert response.status_code == 204
        assert db.get_project(project.id).tags == []

    def test_add_single_tag(self, client, headers):
        project = db.create_project(name="p7", domain_id="default")

        response = client.put(f"/v3/projects/{project.id}/tags/decommissioned", headers=headers)
        assert response.status_code == 201
        assert response.headers["Location"].endswith(
            f"/v3/projects/{project.id}/tags/decommissioned"
        )
        assert db.get_project(project.id).tags == ["decommissioned"]

    def test_add_single_tag_is_idempotent(self, client, headers):
        project = db.create_project(name="p8", domain_id="default", tags=["once"])

        client.put(f"/v3/projects/{project.id}/tags/once", headers=headers)
        assert db.get_project(project.id).tags == ["once"]

    def test_check_tag_present_and_absent(self, client, headers):
        project = db.create_project(name="p9", domain_id="default", tags=["here"])

        assert (
            client.get(f"/v3/projects/{project.id}/tags/here", headers=headers).status_code == 204
        )
        assert (
            client.get(f"/v3/projects/{project.id}/tags/gone", headers=headers).status_code == 404
        )

    def test_delete_single_tag(self, client, headers):
        project = db.create_project(name="p10", domain_id="default", tags=["a", "b"])

        response = client.delete(f"/v3/projects/{project.id}/tags/a", headers=headers)
        assert response.status_code == 204
        assert db.get_project(project.id).tags == ["b"]

    def test_delete_missing_tag_is_404(self, client, headers):
        project = db.create_project(name="p11", domain_id="default")

        response = client.delete(f"/v3/projects/{project.id}/tags/nope", headers=headers)
        assert response.status_code == 404

    def test_unknown_project_is_404(self, client, headers):
        assert client.get("/v3/projects/missing/tags", headers=headers).status_code == 404
        assert client.put("/v3/projects/missing/tags/x", headers=headers).status_code == 404


class TestProjectTagValidation:
    """Tags follow the API-WG guideline Keystone's schema enforces."""

    def test_comma_is_rejected(self, client, headers):
        project = db.create_project(name="v1", domain_id="default")

        response = client.put(
            f"/v3/projects/{project.id}/tags", headers=headers, json={"tags": ["a,b"]}
        )
        assert response.status_code == 400

    def test_slash_is_rejected(self, client, headers):
        project = db.create_project(name="v2", domain_id="default")

        response = client.put(
            f"/v3/projects/{project.id}/tags", headers=headers, json={"tags": ["a/b"]}
        )
        assert response.status_code == 400

    def test_over_long_tag_is_rejected(self, client, headers):
        project = db.create_project(name="v3", domain_id="default")

        response = client.put(
            f"/v3/projects/{project.id}/tags", headers=headers, json={"tags": ["x" * 256]}
        )
        assert response.status_code == 400

    def test_more_than_eighty_tags_is_rejected(self, client, headers):
        project = db.create_project(name="v4", domain_id="default")

        response = client.put(
            f"/v3/projects/{project.id}/tags",
            headers=headers,
            json={"tags": [f"tag-{i}" for i in range(81)]},
        )
        assert response.status_code == 400


class TestProjectTagFilters:
    """The four Identity API tag filters on GET /v3/projects."""

    @pytest.fixture(autouse=True)
    def projects(self):
        db.create_project(name="alpha", domain_id="default", tags=["waldur", "prod"])
        db.create_project(name="beta", domain_id="default", tags=["waldur"])
        db.create_project(name="gamma", domain_id="default", tags=["prod"])
        db.create_project(name="delta", domain_id="default")

    def _names(self, response):
        return sorted(p["name"] for p in response.json()["projects"])

    def test_tags_matches_all(self, client, headers):
        response = client.get("/v3/projects?tags=waldur,prod", headers=headers)
        assert self._names(response) == ["alpha"]

    def test_tags_any_matches_at_least_one(self, client, headers):
        response = client.get("/v3/projects?tags-any=waldur,prod", headers=headers)
        assert self._names(response) == ["alpha", "beta", "gamma"]

    def test_not_tags_excludes_full_match(self, client, headers):
        response = client.get("/v3/projects?not-tags=waldur,prod", headers=headers)
        assert "alpha" not in self._names(response)

    def test_not_tags_any_excludes_any_match(self, client, headers):
        response = client.get("/v3/projects?not-tags-any=waldur", headers=headers)
        names = self._names(response)
        assert "alpha" not in names
        assert "beta" not in names
        assert "gamma" in names
        assert "delta" in names
