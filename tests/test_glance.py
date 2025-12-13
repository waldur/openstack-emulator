"""Tests for Glance Image API emulator."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    db.reset_glance()
    yield


apps = create_all_service_apps()
client = TestClient(apps["glance"])


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "glance"


class TestVersions:
    """Test API versions endpoint."""

    def test_get_versions(self):
        """Test getting API versions."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) > 0
        # Check current version exists
        current = [v for v in data["versions"] if v["status"] == "CURRENT"]
        assert len(current) == 1


class TestImages:
    """Test image CRUD operations."""

    def test_list_images(self):
        """Test listing images."""
        response = client.get("/v2/images")
        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        assert "schema" in data
        # Default images should exist
        assert len(data["images"]) >= 3

    def test_list_images_with_filters(self):
        """Test listing images with filters."""
        response = client.get("/v2/images?visibility=public")
        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        for image in data["images"]:
            assert image["visibility"] == "public"

    def test_list_images_with_pagination(self):
        """Test listing images with pagination."""
        response = client.get("/v2/images?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["images"]) == 1

    def test_create_image(self):
        """Test creating an image."""
        response = client.post(
            "/v2/images",
            json={
                "name": "test-image",
                "visibility": "private",
                "container_format": "bare",
                "disk_format": "qcow2",
                "min_disk": 5,
                "min_ram": 256,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-image"
        assert data["status"] == "queued"
        assert data["visibility"] == "private"
        assert data["container_format"] == "bare"
        assert data["disk_format"] == "qcow2"
        assert data["min_disk"] == 5
        assert data["min_ram"] == 256

    def test_create_image_minimal(self):
        """Test creating an image with minimal data."""
        response = client.post("/v2/images", json={"name": "minimal-image"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "minimal-image"
        assert data["status"] == "queued"

    def test_get_image(self):
        """Test getting a specific image."""
        # First list to get an image ID
        list_response = client.get("/v2/images")
        images = list_response.json()["images"]
        image_id = images[0]["id"]

        response = client.get(f"/v2/images/{image_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == image_id

    def test_get_image_not_found(self):
        """Test getting non-existent image."""
        response = client.get("/v2/images/non-existent-id")
        assert response.status_code == 404

    def test_update_image(self):
        """Test updating an image using JSON Patch."""
        # Create an image first
        create_response = client.post(
            "/v2/images",
            json={"name": "update-test"},
        )
        image_id = create_response.json()["id"]

        # Update using JSON Patch
        response = client.patch(
            f"/v2/images/{image_id}",
            json=[
                {"op": "replace", "path": "/name", "value": "updated-name"},
                {"op": "replace", "path": "/min_disk", "value": 10},
            ],
            headers={"Content-Type": "application/openstack-images-v2.1-json-patch"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "updated-name"
        assert data["min_disk"] == 10

    def test_delete_image(self):
        """Test deleting an image."""
        # Create an image first
        create_response = client.post(
            "/v2/images",
            json={"name": "delete-test"},
        )
        image_id = create_response.json()["id"]

        # Delete the image
        response = client.delete(f"/v2/images/{image_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/v2/images/{image_id}")
        assert get_response.status_code == 404

    def test_delete_protected_image(self):
        """Test that protected images cannot be deleted."""
        # Create a protected image
        create_response = client.post(
            "/v2/images",
            json={"name": "protected-image", "protected": True},
        )
        image_id = create_response.json()["id"]

        # Try to delete - should fail
        response = client.delete(f"/v2/images/{image_id}")
        assert response.status_code == 403


class TestImageData:
    """Test image file upload/download."""

    def test_upload_image_data(self):
        """Test uploading image data."""
        # Create an image first
        create_response = client.post(
            "/v2/images",
            json={
                "name": "upload-test",
                "container_format": "bare",
                "disk_format": "raw",
            },
        )
        image_id = create_response.json()["id"]

        # Upload data
        response = client.put(
            f"/v2/images/{image_id}/file",
            content=b"fake image data",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 204

        # Verify image is now active
        get_response = client.get(f"/v2/images/{image_id}")
        data = get_response.json()
        assert data["status"] == "active"
        assert data["size"] == len(b"fake image data")

    def test_download_image_data(self):
        """Test downloading image data."""
        # Get an active image
        list_response = client.get("/v2/images?status=active")
        images = list_response.json()["images"]
        if not images:
            pytest.skip("No active images available")

        image_id = images[0]["id"]

        # Download data
        response = client.get(f"/v2/images/{image_id}/file")
        assert response.status_code == 200


class TestImageActions:
    """Test image actions."""

    def test_deactivate_image(self):
        """Test deactivating an image."""
        # Get an active image
        list_response = client.get("/v2/images?status=active")
        images = list_response.json()["images"]
        if not images:
            pytest.skip("No active images available")

        image_id = images[0]["id"]

        # Deactivate
        response = client.post(f"/v2/images/{image_id}/actions/deactivate")
        assert response.status_code == 204

        # Verify status
        get_response = client.get(f"/v2/images/{image_id}")
        assert get_response.json()["status"] == "deactivated"

    def test_reactivate_image(self):
        """Test reactivating an image."""
        # Get an active image and deactivate it
        list_response = client.get("/v2/images?status=active")
        images = list_response.json()["images"]
        if not images:
            pytest.skip("No active images available")

        image_id = images[0]["id"]
        client.post(f"/v2/images/{image_id}/actions/deactivate")

        # Reactivate
        response = client.post(f"/v2/images/{image_id}/actions/reactivate")
        assert response.status_code == 204

        # Verify status
        get_response = client.get(f"/v2/images/{image_id}")
        assert get_response.json()["status"] == "active"


class TestImageTags:
    """Test image tag operations."""

    def test_add_tag(self):
        """Test adding a tag to an image."""
        # Create an image
        create_response = client.post(
            "/v2/images",
            json={"name": "tag-test"},
        )
        image_id = create_response.json()["id"]

        # Add tag
        response = client.put(f"/v2/images/{image_id}/tags/test-tag")
        assert response.status_code == 204

        # Verify tag is present
        get_response = client.get(f"/v2/images/{image_id}")
        assert "test-tag" in get_response.json()["tags"]

    def test_delete_tag(self):
        """Test deleting a tag from an image."""
        # Create an image with a tag
        create_response = client.post(
            "/v2/images",
            json={"name": "tag-delete-test", "tags": ["delete-me"]},
        )
        image_id = create_response.json()["id"]

        # Delete tag
        response = client.delete(f"/v2/images/{image_id}/tags/delete-me")
        assert response.status_code == 204

        # Verify tag is gone
        get_response = client.get(f"/v2/images/{image_id}")
        assert "delete-me" not in get_response.json()["tags"]


class TestImageMembers:
    """Test image sharing (members) operations."""

    def test_list_members_empty(self):
        """Test listing members of an image with no members."""
        # Create a shared image
        create_response = client.post(
            "/v2/images",
            json={"name": "shared-image", "visibility": "shared"},
        )
        image_id = create_response.json()["id"]

        response = client.get(f"/v2/images/{image_id}/members")
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert len(data["members"]) == 0

    def test_add_member(self):
        """Test adding a member to a shared image."""
        # Create a shared image
        create_response = client.post(
            "/v2/images",
            json={"name": "shared-image", "visibility": "shared"},
        )
        image_id = create_response.json()["id"]

        # Add member
        response = client.post(
            f"/v2/images/{image_id}/members",
            json={"member": "project-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["member_id"] == "project-123"
        assert data["status"] == "pending"

    def test_add_member_to_non_shared_image_fails(self):
        """Test that adding a member to a non-shared image fails."""
        # Create a private image
        create_response = client.post(
            "/v2/images",
            json={"name": "private-image", "visibility": "private"},
        )
        image_id = create_response.json()["id"]

        # Try to add member - should fail
        response = client.post(
            f"/v2/images/{image_id}/members",
            json={"member": "project-123"},
        )
        assert response.status_code == 403

    def test_update_member_status(self):
        """Test updating member status."""
        # Create a shared image with a member
        create_response = client.post(
            "/v2/images",
            json={"name": "shared-image", "visibility": "shared"},
        )
        image_id = create_response.json()["id"]
        client.post(
            f"/v2/images/{image_id}/members",
            json={"member": "project-123"},
        )

        # Update member status
        response = client.put(
            f"/v2/images/{image_id}/members/project-123",
            json={"status": "accepted"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    def test_delete_member(self):
        """Test deleting a member from an image."""
        # Create a shared image with a member
        create_response = client.post(
            "/v2/images",
            json={"name": "shared-image", "visibility": "shared"},
        )
        image_id = create_response.json()["id"]
        client.post(
            f"/v2/images/{image_id}/members",
            json={"member": "project-123"},
        )

        # Delete member
        response = client.delete(f"/v2/images/{image_id}/members/project-123")
        assert response.status_code == 204

        # Verify member is gone
        get_response = client.get(f"/v2/images/{image_id}/members")
        members = get_response.json()["members"]
        assert not any(m["member_id"] == "project-123" for m in members)


class TestSchemas:
    """Test schema endpoints."""

    def test_get_image_schema(self):
        """Test getting image schema."""
        response = client.get("/v2/schemas/image")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "image"
        assert "properties" in data

    def test_get_images_schema(self):
        """Test getting images collection schema."""
        response = client.get("/v2/schemas/images")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "images"

    def test_get_member_schema(self):
        """Test getting member schema."""
        response = client.get("/v2/schemas/member")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "member"

    def test_get_members_schema(self):
        """Test getting members collection schema."""
        response = client.get("/v2/schemas/members")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "members"


class TestDefaultImages:
    """Test that default images are available."""

    def test_default_images_exist(self):
        """Test that default images are created."""
        response = client.get("/v2/images")
        images = response.json()["images"]

        # Should have at least 3 default images
        assert len(images) >= 3

        # Check for expected images
        names = [img["name"] for img in images]
        assert "cirros-0.6.2-x86_64" in names
        assert "ubuntu-22.04-server" in names
        assert "debian-12-genericcloud" in names

    def test_default_images_are_public(self):
        """Test that default images are public."""
        response = client.get("/v2/images?visibility=public")
        images = response.json()["images"]
        assert len(images) >= 3

    def test_default_images_are_active(self):
        """Test that default images are active."""
        response = client.get("/v2/images?status=active")
        images = response.json()["images"]
        assert len(images) >= 3
