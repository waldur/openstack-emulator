"""Test Cinder extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

# Create Cinder app for testing
service_apps = create_all_service_apps()
cinder_app = service_apps["cinder"]
client = TestClient(cinder_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._volumes.clear()
    db._snapshots.clear()
    db._volume_types.clear()
    db._volume_transfers.clear()
    db._volume_backups.clear()
    db._consistency_groups.clear()
    db._group_snapshots.clear()
    db._tokens.clear()
    db._init_default_volume_types()
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
def test_volume(auth_token):
    """Create a test volume."""
    response = client.post(
        "/v3/admin/volumes",
        json={
            "volume": {
                "name": "test-volume",
                "size": 1,
            }
        },
        headers={"X-Auth-Token": auth_token},
    )
    assert response.status_code == 202
    return response.json()["volume"]["id"]


class TestVolumeTransfers:
    """Test volume transfer endpoints."""

    def test_list_volume_transfers_empty(self, auth_token):
        """Test listing volume transfers when none exist."""
        response = client.get(
            "/v3/admin/os-volume-transfer",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "transfers" in data
        assert data["transfers"] == []

    def test_create_volume_transfer(self, auth_token, test_volume):
        """Test creating a volume transfer."""
        response = client.post(
            "/v3/admin/os-volume-transfer",
            json={
                "transfer": {
                    "name": "test-transfer",
                    "volume_id": test_volume,
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        data = response.json()
        assert "transfer" in data
        assert data["transfer"]["name"] == "test-transfer"
        assert data["transfer"]["volume_id"] == test_volume
        assert "auth_key" in data["transfer"]

    def test_get_volume_transfer(self, auth_token, test_volume):
        """Test getting a volume transfer by ID."""
        # Create a transfer first
        create_response = client.post(
            "/v3/admin/os-volume-transfer",
            json={"transfer": {"name": "get-test-transfer", "volume_id": test_volume}},
            headers={"X-Auth-Token": auth_token},
        )
        transfer_id = create_response.json()["transfer"]["id"]

        # Get the transfer
        response = client.get(
            f"/v3/admin/os-volume-transfer/{transfer_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["transfer"]["id"] == transfer_id
        assert data["transfer"]["name"] == "get-test-transfer"

    def test_delete_volume_transfer(self, auth_token, test_volume):
        """Test deleting a volume transfer."""
        # Create a transfer first
        create_response = client.post(
            "/v3/admin/os-volume-transfer",
            json={"transfer": {"name": "delete-test-transfer", "volume_id": test_volume}},
            headers={"X-Auth-Token": auth_token},
        )
        transfer_id = create_response.json()["transfer"]["id"]

        # Delete the transfer
        response = client.delete(
            f"/v3/admin/os-volume-transfer/{transfer_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify it's deleted
        response = client.get(
            f"/v3/admin/os-volume-transfer/{transfer_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestVolumeBackups:
    """Test volume backup endpoints."""

    def test_list_volume_backups_empty(self, auth_token):
        """Test listing volume backups when none exist."""
        response = client.get(
            "/v3/admin/backups",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "backups" in data
        assert data["backups"] == []

    def test_create_volume_backup(self, auth_token, test_volume):
        """Test creating a volume backup."""
        response = client.post(
            "/v3/admin/backups",
            json={
                "backup": {
                    "name": "test-backup",
                    "volume_id": test_volume,
                    "description": "Test backup",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        data = response.json()
        assert "backup" in data
        assert data["backup"]["name"] == "test-backup"
        assert data["backup"]["volume_id"] == test_volume
        assert data["backup"]["status"] == "available"

    def test_get_volume_backup(self, auth_token, test_volume):
        """Test getting a volume backup by ID."""
        # Create a backup first
        create_response = client.post(
            "/v3/admin/backups",
            json={"backup": {"name": "get-test-backup", "volume_id": test_volume}},
            headers={"X-Auth-Token": auth_token},
        )
        backup_id = create_response.json()["backup"]["id"]

        # Get the backup
        response = client.get(
            f"/v3/admin/backups/{backup_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["backup"]["id"] == backup_id
        assert data["backup"]["name"] == "get-test-backup"

    def test_delete_volume_backup(self, auth_token, test_volume):
        """Test deleting a volume backup."""
        # Create a backup first
        create_response = client.post(
            "/v3/admin/backups",
            json={"backup": {"name": "delete-test-backup", "volume_id": test_volume}},
            headers={"X-Auth-Token": auth_token},
        )
        backup_id = create_response.json()["backup"]["id"]

        # Delete the backup
        response = client.delete(
            f"/v3/admin/backups/{backup_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify it's deleted
        response = client.get(
            f"/v3/admin/backups/{backup_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404

    def test_restore_volume_backup(self, auth_token, test_volume):
        """Test restoring a volume from backup."""
        # Create a backup first
        create_response = client.post(
            "/v3/admin/backups",
            json={"backup": {"name": "restore-test-backup", "volume_id": test_volume}},
            headers={"X-Auth-Token": auth_token},
        )
        backup_id = create_response.json()["backup"]["id"]

        # Restore the backup to a new volume
        response = client.post(
            f"/v3/admin/backups/{backup_id}/restore",
            json={
                "restore": {
                    "name": "restored-volume",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        data = response.json()
        assert "restore" in data
        assert data["restore"]["backup_id"] == backup_id
        assert "volume_id" in data["restore"]


class TestConsistencyGroups:
    """Test consistency group endpoints."""

    def test_list_consistency_groups_empty(self, auth_token):
        """Test listing consistency groups when none exist."""
        response = client.get(
            "/v3/admin/groups",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "groups" in data
        assert data["groups"] == []

    def test_create_consistency_group(self, auth_token):
        """Test creating a consistency group."""
        response = client.post(
            "/v3/admin/groups",
            json={
                "group": {
                    "name": "test-group",
                    "description": "Test consistency group",
                    "volume_types": ["lvmdriver-1"],
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        data = response.json()
        assert "group" in data
        assert data["group"]["name"] == "test-group"
        assert data["group"]["description"] == "Test consistency group"
        assert data["group"]["status"] == "available"

    def test_get_consistency_group(self, auth_token):
        """Test getting a consistency group by ID."""
        # Create a group first
        create_response = client.post(
            "/v3/admin/groups",
            json={"group": {"name": "get-test-group", "volume_types": ["lvmdriver-1"]}},
            headers={"X-Auth-Token": auth_token},
        )
        group_id = create_response.json()["group"]["id"]

        # Get the group
        response = client.get(
            f"/v3/admin/groups/{group_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["group"]["id"] == group_id
        assert data["group"]["name"] == "get-test-group"

    def test_delete_consistency_group(self, auth_token):
        """Test deleting a consistency group."""
        # Create a group first
        create_response = client.post(
            "/v3/admin/groups",
            json={"group": {"name": "delete-test-group", "volume_types": ["lvmdriver-1"]}},
            headers={"X-Auth-Token": auth_token},
        )
        group_id = create_response.json()["group"]["id"]

        # Delete the group
        response = client.delete(
            f"/v3/admin/groups/{group_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        # Verify it's deleted
        response = client.get(
            f"/v3/admin/groups/{group_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestGroupSnapshots:
    """Test group snapshot endpoints."""

    def test_list_group_snapshots_empty(self, auth_token):
        """Test listing group snapshots when none exist."""
        response = client.get(
            "/v3/admin/group_snapshots",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "group_snapshots" in data
        assert data["group_snapshots"] == []

    def test_create_group_snapshot(self, auth_token):
        """Test creating a group snapshot."""
        # Create a consistency group first
        group_response = client.post(
            "/v3/admin/groups",
            json={"group": {"name": "snapshot-test-group", "volume_types": ["lvmdriver-1"]}},
            headers={"X-Auth-Token": auth_token},
        )
        group_id = group_response.json()["group"]["id"]

        # Create a group snapshot
        response = client.post(
            "/v3/admin/group_snapshots",
            json={
                "group_snapshot": {
                    "name": "test-group-snapshot",
                    "group_id": group_id,
                    "description": "Test group snapshot",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 202

        data = response.json()
        assert "group_snapshot" in data
        assert data["group_snapshot"]["name"] == "test-group-snapshot"
        assert data["group_snapshot"]["group_id"] == group_id
        assert data["group_snapshot"]["status"] == "available"
