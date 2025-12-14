"""Test Glance extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

# Create Glance app for testing
service_apps = create_all_service_apps()
glance_app = service_apps["glance"]
client = TestClient(glance_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._glance_images.clear()
    db._image_members.clear()
    db._image_tasks.clear()
    db._metadef_namespaces.clear()
    db._image_cache.clear()
    db._tokens.clear()
    db._init_default_glance_images()
    db._init_glance_extensions()
    db.reset_keystone()
    yield


@pytest.fixture
def auth_token():
    """Get a valid auth token for testing."""
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
def test_image(auth_token):
    """Create a test image."""
    response = client.post(
        "/v2/images",
        json={
            "name": "test-image",
            "container_format": "bare",
            "disk_format": "qcow2",
        },
        headers={"X-Auth-Token": auth_token},
    )
    assert response.status_code == 201
    return response.json()["id"]


class TestImageTasks:
    """Test image task endpoints."""

    def test_list_tasks_empty(self, auth_token):
        """Test listing tasks when none exist."""
        response = client.get("/v2/tasks", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "tasks" in data
        assert data["tasks"] == []

    def test_create_import_task(self, auth_token):
        """Test creating an import task."""
        response = client.post(
            "/v2/tasks",
            json={
                "type": "import",
                "input": {
                    "image_properties": {
                        "name": "imported-image",
                        "container_format": "bare",
                        "disk_format": "qcow2",
                    },
                    "import_from": "http://example.com/image.qcow2",
                },
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "task" in data
        assert data["task"]["type"] == "import"
        assert data["task"]["status"] == "success"  # Simulated immediate success

    def test_get_task(self, auth_token):
        """Test getting a task by ID."""
        # Create a task first
        create_response = client.post(
            "/v2/tasks",
            json={"type": "import", "input": {"test": "data"}},
            headers={"X-Auth-Token": auth_token},
        )
        task_id = create_response.json()["task"]["id"]

        # Get the task
        response = client.get(f"/v2/tasks/{task_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert data["task"]["id"] == task_id
        assert data["task"]["type"] == "import"

    def test_delete_task(self, auth_token):
        """Test deleting a task."""
        # Create a task first
        create_response = client.post(
            "/v2/tasks",
            json={"type": "export", "input": {"image_id": "test-id"}},
            headers={"X-Auth-Token": auth_token},
        )
        task_id = create_response.json()["task"]["id"]

        # Delete the task
        response = client.delete(f"/v2/tasks/{task_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(f"/v2/tasks/{task_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 404


class TestMetadefNamespaces:
    """Test metadata definition namespace endpoints."""

    def test_list_metadef_namespaces_empty(self, auth_token):
        """Test listing namespaces when none exist."""
        response = client.get("/v2/metadefs/namespaces", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "namespaces" in data
        assert data["namespaces"] == []

    def test_create_metadef_namespace(self, auth_token):
        """Test creating a metadata definition namespace."""
        response = client.post(
            "/v2/metadefs/namespaces",
            json={
                "namespace": "test-namespace",
                "display_name": "Test Namespace",
                "description": "Test metadata namespace",
                "visibility": "private",
                "properties": {
                    "test_property": {
                        "type": "string",
                        "description": "A test property",
                    }
                },
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert data["namespace"] == "test-namespace"
        assert data["display_name"] == "Test Namespace"
        assert data["visibility"] == "private"

    def test_get_metadef_namespace(self, auth_token):
        """Test getting a metadata definition namespace."""
        # Create a namespace first
        create_response = client.post(
            "/v2/metadefs/namespaces",
            json={"namespace": "get-test-namespace", "display_name": "Get Test"},
            headers={"X-Auth-Token": auth_token},
        )

        # Get the namespace
        response = client.get(
            "/v2/metadefs/namespaces/get-test-namespace",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["namespace"] == "get-test-namespace"
        assert data["display_name"] == "Get Test"

    def test_delete_metadef_namespace(self, auth_token):
        """Test deleting a metadata definition namespace."""
        # Create a namespace first
        client.post(
            "/v2/metadefs/namespaces",
            json={"namespace": "delete-test-namespace"},
            headers={"X-Auth-Token": auth_token},
        )

        # Delete the namespace
        response = client.delete(
            "/v2/metadefs/namespaces/delete-test-namespace",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            "/v2/metadefs/namespaces/delete-test-namespace",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestImageCache:
    """Test image cache endpoints."""

    def test_get_cache_status_empty(self, auth_token):
        """Test getting cache status when empty."""
        response = client.get("/v2/cache", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "cached_images" in data
        assert "queued_images" in data
        assert data["cache_count"] == 0
        assert data["total_size"] == 0

    def test_cache_image(self, auth_token, test_image):
        """Test caching an image."""
        response = client.put(f"/v2/cache/{test_image}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 202

        # Check cache status
        status_response = client.get("/v2/cache", headers={"X-Auth-Token": auth_token})
        data = status_response.json()
        assert data["cache_count"] >= 1

    def test_clear_cache(self, auth_token, test_image):
        """Test clearing the image cache."""
        # Cache an image first
        client.put(f"/v2/cache/{test_image}", headers={"X-Auth-Token": auth_token})

        # Clear cache
        response = client.delete("/v2/cache", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 204

        # Verify cache is empty
        status_response = client.get("/v2/cache", headers={"X-Auth-Token": auth_token})
        data = status_response.json()
        assert data["cache_count"] == 0


class TestImageDiscovery:
    """Test image discovery endpoints."""

    def test_get_stores_info(self, auth_token):
        """Test getting stores information."""
        response = client.get("/v2/info/stores", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "stores" in data
        assert len(data["stores"]) > 0

        # Check for expected stores
        store_types = [store["type"] for store in data["stores"]]
        assert "file" in store_types

    def test_get_import_info(self, auth_token):
        """Test getting import methods information."""
        response = client.get("/v2/info/import", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "import-methods" in data
        assert "import-methods-list" in data

        # Check for expected import methods
        method_names = [method["name"] for method in data["import-methods-list"]]
        assert "glance-direct" in method_names
        assert "web-download" in method_names


class TestImageSchemas:
    """Test additional schema endpoints."""

    def test_get_task_schema(self, auth_token):
        """Test getting task schema."""
        response = client.get("/v2/schemas/task", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "task"
        assert "properties" in data
        assert "id" in data["properties"]
        assert "type" in data["properties"]
        assert "status" in data["properties"]

    def test_get_tasks_schema(self, auth_token):
        """Test getting tasks collection schema."""
        response = client.get("/v2/schemas/tasks", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "tasks"
        assert "properties" in data
        assert "tasks" in data["properties"]

    def test_get_metadef_namespace_schema(self, auth_token):
        """Test getting metadef namespace schema."""
        response = client.get(
            "/v2/schemas/metadefs/namespace", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "namespace"
        assert "properties" in data
        assert "namespace" in data["properties"]
        assert "visibility" in data["properties"]
