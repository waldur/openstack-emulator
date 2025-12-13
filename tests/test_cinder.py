"""Tests for Cinder Block Storage API endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    db._servers.clear()
    db._tokens.clear()
    db._keypairs.clear()
    db._volumes.clear()
    db._snapshots.clear()
    db._volume_types.clear()
    db._qos_specs.clear()
    db._init_default_flavors()
    db._init_default_images()
    db._init_default_volume_types()
    db.reset_keystone()
    yield


@pytest.fixture
def client():
    """Create test client."""
    apps = create_all_service_apps()
    return TestClient(apps["cinder"])


@pytest.fixture
def auth_token(client):
    """Get an authentication token by creating it directly in the database."""
    # Create token directly in database for simplified testing
    token = db.create_token(
        user_name="admin",
        project_name="admin", 
        domain_id="default"
    )
    return token.id


@pytest.fixture
def project_id(client, auth_token):
    """Get the project ID from the database."""
    # Since we create tokens directly, we can return the default project ID
    token = db.validate_token(auth_token)
    return token.project_id if token else "admin"


class TestVersionEndpoints:
    """Test version discovery endpoints."""

    def test_cinder_volumes_endpoint_works(self, client, auth_token, project_id):
        """Test that Cinder volumes endpoint is accessible."""
        response = client.get(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "volumes" in data


class TestVolumeEndpoints:
    """Test volume endpoints."""

    def test_list_volumes_empty(self, client, auth_token, project_id):
        """Test listing volumes when none exist."""
        response = client.get(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "volumes" in data
        assert len(data["volumes"]) == 0

    def test_create_volume(self, client, auth_token, project_id):
        """Test creating a volume."""
        response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        assert response.status_code == 202
        data = response.json()
        assert "volume" in data
        assert data["volume"]["name"] == "test-volume"
        assert data["volume"]["size"] == 10
        assert data["volume"]["status"] == "available"

    def test_create_volume_with_description(self, client, auth_token, project_id):
        """Test creating a volume with description."""
        response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume": {
                    "name": "test-volume",
                    "size": 5,
                    "description": "Test description",
                }
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["volume"]["description"] == "Test description"

    def test_list_volumes(self, client, auth_token, project_id):
        """Test listing volumes."""
        # Create a volume first
        client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )

        response = client.get(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["volumes"]) == 1

    def test_list_volumes_detail(self, client, auth_token, project_id):
        """Test listing volumes with details."""
        # Create a volume first
        client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )

        response = client.get(
            f"/v3/{project_id}/volumes/detail",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["volumes"]) == 1
        assert "status" in data["volumes"][0]
        assert "size" in data["volumes"][0]
        assert "volume_type" in data["volumes"][0]

    def test_show_volume(self, client, auth_token, project_id):
        """Test showing volume details."""
        # Create a volume first
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.get(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume"]["id"] == volume_id
        assert data["volume"]["name"] == "test-volume"

    def test_show_volume_not_found(self, client, auth_token, project_id):
        """Test showing non-existent volume."""
        response = client.get(
            f"/v3/{project_id}/volumes/non-existent-id",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_update_volume(self, client, auth_token, project_id):
        """Test updating a volume."""
        # Create a volume first
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.put(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "updated-volume", "description": "Updated"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume"]["name"] == "updated-volume"
        assert data["volume"]["description"] == "Updated"

    def test_delete_volume(self, client, auth_token, project_id):
        """Test deleting a volume."""
        # Create a volume first
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.delete(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify volume is deleted
        response = client.get(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_extend_volume(self, client, auth_token, project_id):
        """Test extending a volume."""
        # Create a volume first
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.post(
            f"/v3/{project_id}/volumes/{volume_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"os-extend": {"new_size": 20}},
        )
        assert response.status_code == 202

        # Verify volume size
        show_response = client.get(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert show_response.json()["volume"]["size"] == 20

    def test_set_bootable(self, client, auth_token, project_id):
        """Test setting volume bootable flag."""
        # Create a volume first
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.post(
            f"/v3/{project_id}/volumes/{volume_id}/action",
            headers={"X-Auth-Token": auth_token},
            json={"os-set_bootable": {"bootable": True}},
        )
        assert response.status_code == 200

        # Verify bootable flag
        show_response = client.get(
            f"/v3/{project_id}/volumes/{volume_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert show_response.json()["volume"]["bootable"] == "true"


class TestVolumeMetadata:
    """Test volume metadata endpoints."""

    def test_list_volume_metadata(self, client, auth_token, project_id):
        """Test listing volume metadata."""
        # Create a volume with metadata
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume": {
                    "name": "test-volume",
                    "size": 10,
                    "metadata": {"key1": "value1"},
                }
            },
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.get(
            f"/v3/{project_id}/volumes/{volume_id}/metadata",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["key1"] == "value1"

    def test_update_volume_metadata(self, client, auth_token, project_id):
        """Test updating volume metadata."""
        # Create a volume
        create_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_response.json()["volume"]["id"]

        response = client.put(
            f"/v3/{project_id}/volumes/{volume_id}/metadata",
            headers={"X-Auth-Token": auth_token},
            json={"metadata": {"key1": "value1", "key2": "value2"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "key1" in data["metadata"]
        assert "key2" in data["metadata"]


class TestSnapshotEndpoints:
    """Test snapshot endpoints."""

    def test_list_snapshots_empty(self, client, auth_token, project_id):
        """Test listing snapshots when none exist."""
        response = client.get(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "snapshots" in data
        assert len(data["snapshots"]) == 0

    def test_create_snapshot(self, client, auth_token, project_id):
        """Test creating a snapshot."""
        # Create a volume first
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        response = client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={
                "snapshot": {
                    "name": "test-snapshot",
                    "volume_id": volume_id,
                    "description": "Test snapshot",
                }
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "snapshot" in data
        assert data["snapshot"]["name"] == "test-snapshot"
        assert data["snapshot"]["volume_id"] == volume_id
        assert data["snapshot"]["status"] == "available"

    def test_list_snapshots(self, client, auth_token, project_id):
        """Test listing snapshots."""
        # Create a volume and snapshot
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "test-snapshot", "volume_id": volume_id}},
        )

        response = client.get(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["snapshots"]) == 1

    def test_list_snapshots_detail(self, client, auth_token, project_id):
        """Test listing snapshots with details."""
        # Create a volume and snapshot
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "test-snapshot", "volume_id": volume_id}},
        )

        response = client.get(
            f"/v3/{project_id}/snapshots/detail",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["snapshots"]) == 1
        assert "status" in data["snapshots"][0]
        assert "volume_id" in data["snapshots"][0]

    def test_show_snapshot(self, client, auth_token, project_id):
        """Test showing snapshot details."""
        # Create a volume and snapshot
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        create_snap_response = client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "test-snapshot", "volume_id": volume_id}},
        )
        snapshot_id = create_snap_response.json()["snapshot"]["id"]

        response = client.get(
            f"/v3/{project_id}/snapshots/{snapshot_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["snapshot"]["id"] == snapshot_id

    def test_update_snapshot(self, client, auth_token, project_id):
        """Test updating a snapshot."""
        # Create a volume and snapshot
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        create_snap_response = client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "test-snapshot", "volume_id": volume_id}},
        )
        snapshot_id = create_snap_response.json()["snapshot"]["id"]

        response = client.put(
            f"/v3/{project_id}/snapshots/{snapshot_id}",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "updated-snapshot", "description": "Updated"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["snapshot"]["name"] == "updated-snapshot"
        assert data["snapshot"]["description"] == "Updated"

    def test_delete_snapshot(self, client, auth_token, project_id):
        """Test deleting a snapshot."""
        # Create a volume and snapshot
        create_vol_response = client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )
        volume_id = create_vol_response.json()["volume"]["id"]

        create_snap_response = client.post(
            f"/v3/{project_id}/snapshots",
            headers={"X-Auth-Token": auth_token},
            json={"snapshot": {"name": "test-snapshot", "volume_id": volume_id}},
        )
        snapshot_id = create_snap_response.json()["snapshot"]["id"]

        response = client.delete(
            f"/v3/{project_id}/snapshots/{snapshot_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify snapshot is deleted
        response = client.get(
            f"/v3/{project_id}/snapshots/{snapshot_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestVolumeTypeEndpoints:
    """Test volume type endpoints."""

    def test_list_volume_types(self, client, auth_token, project_id):
        """Test listing volume types."""
        response = client.get(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "volume_types" in data
        assert len(data["volume_types"]) >= 2  # Default types

    def test_create_volume_type(self, client, auth_token, project_id):
        """Test creating a volume type."""
        response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume_type": {
                    "name": "test-ssd",
                    "description": "SSD storage type",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume_type"]["name"] == "test-ssd"
        assert data["volume_type"]["description"] == "SSD storage type"

    def test_create_duplicate_volume_type(self, client, auth_token, project_id):
        """Test creating a duplicate volume type."""
        # Create first type
        client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-duplicate-ssd"}},
        )

        # Try to create duplicate
        response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-duplicate-ssd"}},
        )
        assert response.status_code == 409

    def test_show_volume_type(self, client, auth_token, project_id):
        """Test showing volume type details."""
        # Create a volume type
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-show-ssd"}},
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.get(
            f"/v3/{project_id}/types/{type_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume_type"]["id"] == type_id

    def test_update_volume_type(self, client, auth_token, project_id):
        """Test updating a volume type."""
        # Create a volume type
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-update-ssd"}},
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.put(
            f"/v3/{project_id}/types/{type_id}",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume_type": {
                    "name": "fast-ssd",
                    "description": "Fast SSD storage",
                }
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["volume_type"]["name"] == "fast-ssd"
        assert data["volume_type"]["description"] == "Fast SSD storage"

    def test_delete_volume_type(self, client, auth_token, project_id):
        """Test deleting a volume type."""
        # Create a volume type
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-delete-ssd"}},
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.delete(
            f"/v3/{project_id}/types/{type_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify type is deleted
        response = client.get(
            f"/v3/{project_id}/types/{type_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestVolumeTypeExtraSpecs:
    """Test volume type extra specs endpoints."""

    def test_list_extra_specs(self, client, auth_token, project_id):
        """Test listing volume type extra specs."""
        # Create a volume type with extra specs
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume_type": {
                    "name": "test-extra-specs-ssd",
                    "extra_specs": {"volume_backend_name": "ssd-backend"},
                }
            },
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.get(
            f"/v3/{project_id}/types/{type_id}/extra_specs",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["extra_specs"]["volume_backend_name"] == "ssd-backend"

    def test_create_extra_specs(self, client, auth_token, project_id):
        """Test creating volume type extra specs."""
        # Create a volume type
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={"volume_type": {"name": "test-create-specs-ssd"}},
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.post(
            f"/v3/{project_id}/types/{type_id}/extra_specs",
            headers={"X-Auth-Token": auth_token},
            json={"extra_specs": {"key1": "value1", "key2": "value2"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["extra_specs"]["key1"] == "value1"
        assert data["extra_specs"]["key2"] == "value2"

    def test_delete_extra_spec(self, client, auth_token, project_id):
        """Test deleting a volume type extra spec."""
        # Create a volume type with extra specs
        create_response = client.post(
            f"/v3/{project_id}/types",
            headers={"X-Auth-Token": auth_token},
            json={
                "volume_type": {
                    "name": "test-delete-spec-ssd",
                    "extra_specs": {"key1": "value1"},
                }
            },
        )
        type_id = create_response.json()["volume_type"]["id"]

        response = client.delete(
            f"/v3/{project_id}/types/{type_id}/extra_specs/key1",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202


class TestLimitsEndpoint:
    """Test limits endpoint."""

    def test_get_limits(self, client, auth_token, project_id):
        """Test getting volume limits."""
        response = client.get(
            f"/v3/{project_id}/limits",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "limits" in data
        assert "absolute" in data["limits"]
        assert "maxTotalVolumes" in data["limits"]["absolute"]
        assert "totalVolumesUsed" in data["limits"]["absolute"]

    def test_limits_reflect_usage(self, client, auth_token, project_id):
        """Test that limits reflect actual usage."""
        # Create a volume
        client.post(
            f"/v3/{project_id}/volumes",
            headers={"X-Auth-Token": auth_token},
            json={"volume": {"name": "test-volume", "size": 10}},
        )

        response = client.get(
            f"/v3/{project_id}/limits",
            headers={"X-Auth-Token": auth_token},
        )
        data = response.json()
        assert data["limits"]["absolute"]["totalVolumesUsed"] == 1
        assert data["limits"]["absolute"]["totalGigabytesUsed"] == 10


class TestAvailabilityZones:
    """Test availability zone endpoint."""

    def test_list_availability_zones(self, client, auth_token, project_id):
        """Test listing availability zones."""
        response = client.get(
            f"/v3/{project_id}/os-availability-zone",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "availabilityZoneInfo" in data
        assert len(data["availabilityZoneInfo"]) >= 1
        assert data["availabilityZoneInfo"][0]["zoneName"] == "nova"


class TestAuthenticationRequired:
    """Test that authentication is required for endpoints."""

    def test_list_volumes_without_token(self, client, project_id):
        """Test that listing volumes requires authentication."""
        response = client.get(f"/v3/{project_id}/volumes")
        assert response.status_code == 401

    def test_create_volume_without_token(self, client, project_id):
        """Test that creating volume requires authentication."""
        response = client.post(
            f"/v3/{project_id}/volumes",
            json={"volume": {"name": "test", "size": 1}},
        )
        assert response.status_code == 401

    def test_list_snapshots_without_token(self, client, project_id):
        """Test that listing snapshots requires authentication."""
        response = client.get(f"/v3/{project_id}/snapshots")
        assert response.status_code == 401
