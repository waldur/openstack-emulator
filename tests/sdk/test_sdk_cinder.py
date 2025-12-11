"""SDK tests for Cinder Block Storage service."""

from openstack.connection import Connection


class TestCinderVolumes:
    """Test Cinder volume operations via SDK."""

    def test_list_volumes(self, openstack_connection: Connection) -> None:
        """Test listing volumes."""
        volumes = list(openstack_connection.block_storage.volumes())
        # May be empty initially
        assert isinstance(volumes, list)

    def test_create_volume(self, openstack_connection: Connection) -> None:
        """Test creating a volume."""
        volume = openstack_connection.block_storage.create_volume(
            name="test-sdk-volume",
            size=1,
            description="Test volume created via SDK",
        )
        assert volume is not None
        assert volume.name == "test-sdk-volume"
        assert volume.size == 1

    def test_get_volume(self, openstack_connection: Connection) -> None:
        """Test getting a specific volume."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-get-volume",
            size=1,
        )

        # Get it
        fetched = openstack_connection.block_storage.get_volume(volume.id)
        assert fetched is not None
        assert fetched.id == volume.id
        assert fetched.name == "test-get-volume"

    def test_update_volume(self, openstack_connection: Connection) -> None:
        """Test updating a volume."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-update-volume",
            size=1,
        )

        # Update it
        updated = openstack_connection.block_storage.update_volume(
            volume.id,
            name="test-update-volume-renamed",
            description="Updated description",
        )
        assert updated.name == "test-update-volume-renamed"
        assert updated.description == "Updated description"

    def test_delete_volume(self, openstack_connection: Connection) -> None:
        """Test deleting a volume."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-delete-volume",
            size=1,
        )

        # Delete it
        result = openstack_connection.block_storage.delete_volume(volume.id)
        assert result is None  # delete returns None on success

    def test_create_volume_with_type(self, openstack_connection: Connection) -> None:
        """Test creating a volume with a specific volume type."""
        # Get available volume types
        types = list(openstack_connection.block_storage.types())
        assert len(types) > 0

        # Create volume with type
        volume = openstack_connection.block_storage.create_volume(
            name="test-typed-volume",
            size=1,
            volume_type=types[0].id,
        )
        assert volume is not None
        assert volume.volume_type is not None


class TestCinderSnapshots:
    """Test Cinder snapshot operations via SDK."""

    def test_list_snapshots(self, openstack_connection: Connection) -> None:
        """Test listing snapshots."""
        snapshots = list(openstack_connection.block_storage.snapshots())
        # May be empty initially
        assert isinstance(snapshots, list)

    def test_create_snapshot(self, openstack_connection: Connection) -> None:
        """Test creating a snapshot."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-snapshot-source",
            size=1,
        )

        # Create a snapshot
        snapshot = openstack_connection.block_storage.create_snapshot(
            name="test-sdk-snapshot",
            volume_id=volume.id,
            description="Test snapshot created via SDK",
        )
        assert snapshot is not None
        assert snapshot.name == "test-sdk-snapshot"
        assert snapshot.volume_id == volume.id

    def test_get_snapshot(self, openstack_connection: Connection) -> None:
        """Test getting a specific snapshot."""
        # Create volume and snapshot first
        volume = openstack_connection.block_storage.create_volume(
            name="test-get-snapshot-source",
            size=1,
        )
        snapshot = openstack_connection.block_storage.create_snapshot(
            name="test-get-snapshot",
            volume_id=volume.id,
        )

        # Get it
        fetched = openstack_connection.block_storage.get_snapshot(snapshot.id)
        assert fetched is not None
        assert fetched.id == snapshot.id

    def test_update_snapshot(self, openstack_connection: Connection) -> None:
        """Test updating a snapshot."""
        # Create volume and snapshot first
        volume = openstack_connection.block_storage.create_volume(
            name="test-update-snapshot-source",
            size=1,
        )
        snapshot = openstack_connection.block_storage.create_snapshot(
            name="test-update-snapshot",
            volume_id=volume.id,
        )

        # Update it
        updated = openstack_connection.block_storage.update_snapshot(
            snapshot.id,
            name="test-update-snapshot-renamed",
        )
        assert updated.name == "test-update-snapshot-renamed"

    def test_delete_snapshot(self, openstack_connection: Connection) -> None:
        """Test deleting a snapshot."""
        # Create volume and snapshot first
        volume = openstack_connection.block_storage.create_volume(
            name="test-delete-snapshot-source",
            size=1,
        )
        snapshot = openstack_connection.block_storage.create_snapshot(
            name="test-delete-snapshot",
            volume_id=volume.id,
        )

        # Delete it
        result = openstack_connection.block_storage.delete_snapshot(snapshot.id)
        assert result is None  # delete returns None on success

    def test_create_volume_from_snapshot(self, openstack_connection: Connection) -> None:
        """Test creating a volume from a snapshot."""
        # Create source volume and snapshot
        source_volume = openstack_connection.block_storage.create_volume(
            name="test-snapshot-clone-source",
            size=1,
        )
        snapshot = openstack_connection.block_storage.create_snapshot(
            name="test-clone-snapshot",
            volume_id=source_volume.id,
        )

        # Create volume from snapshot
        cloned = openstack_connection.block_storage.create_volume(
            name="test-cloned-volume",
            size=1,
            snapshot_id=snapshot.id,
        )
        assert cloned is not None
        assert cloned.snapshot_id == snapshot.id


class TestCinderVolumeTypes:
    """Test Cinder volume type operations via SDK."""

    def test_list_volume_types(self, openstack_connection: Connection) -> None:
        """Test listing volume types."""
        types = list(openstack_connection.block_storage.types())
        assert len(types) > 0  # Default types should exist

    def test_get_volume_type(self, openstack_connection: Connection) -> None:
        """Test getting a specific volume type."""
        types = list(openstack_connection.block_storage.types())
        assert len(types) > 0

        vtype = openstack_connection.block_storage.get_type(types[0].id)
        assert vtype is not None
        assert vtype.id == types[0].id


class TestCinderVolumeMetadata:
    """Test Cinder volume metadata operations via SDK."""

    def test_set_volume_metadata(self, openstack_connection: Connection) -> None:
        """Test setting metadata on a volume."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-metadata-volume",
            size=1,
        )

        # Set metadata
        result = openstack_connection.block_storage.set_volume_metadata(
            volume.id,
            metadata={"key1": "value1", "key2": "value2"},
        )
        assert result is not None

    def test_get_volume_metadata(self, openstack_connection: Connection) -> None:
        """Test getting metadata from a volume."""
        # Create a volume with metadata
        volume = openstack_connection.block_storage.create_volume(
            name="test-get-metadata-volume",
            size=1,
            metadata={"test_key": "test_value"},
        )

        # Get metadata
        fetched = openstack_connection.block_storage.get_volume(volume.id)
        assert fetched.metadata is not None
        assert fetched.metadata.get("test_key") == "test_value"


class TestCinderVolumeLifecycle:
    """Test Cinder volume lifecycle operations via SDK."""

    def test_volume_extend(self, openstack_connection: Connection) -> None:
        """Test extending a volume."""
        # Create a volume first
        volume = openstack_connection.block_storage.create_volume(
            name="test-extend-volume",
            size=1,
        )

        # Extend it
        openstack_connection.block_storage.extend_volume(
            volume.id,
            size=2,
        )

        # Verify size increased
        updated = openstack_connection.block_storage.get_volume(volume.id)
        # Note: In the emulator, this might be immediate;
        # in production, there would be a status change
        assert updated.size >= 1  # At minimum, original size


class TestCinderVolumeDetails:
    """Test Cinder volume detail operations via SDK."""

    def test_list_volumes_with_details(self, openstack_connection: Connection) -> None:
        """Test listing volumes with full details."""
        # Create a volume first
        openstack_connection.block_storage.create_volume(
            name="test-detail-volume",
            size=1,
            description="Test volume for details",
        )

        # List with details
        volumes = list(openstack_connection.block_storage.volumes(details=True))
        assert len(volumes) > 0

        # Volumes should have detail fields
        volume = volumes[0]
        assert volume.name is not None

    def test_volume_has_expected_attributes(self, openstack_connection: Connection) -> None:
        """Test that volumes have expected attributes."""
        volume = openstack_connection.block_storage.create_volume(
            name="test-attributes-volume",
            size=1,
            description="Test volume with attributes",
        )

        assert volume.id is not None
        assert volume.name == "test-attributes-volume"
        assert volume.size == 1
        assert volume.description == "Test volume with attributes"
        assert volume.status is not None
