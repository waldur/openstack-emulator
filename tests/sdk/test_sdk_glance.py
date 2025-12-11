"""SDK tests for Glance Image service."""

from openstack.connection import Connection


class TestGlanceImages:
    """Test Glance image operations via SDK."""

    def test_list_images(self, openstack_connection: Connection) -> None:
        """Test listing images."""
        images = list(openstack_connection.image.images())
        assert len(images) > 0

        # Default images should exist (cirros-0.6.2-x86_64 is the default)
        image_names = [i.name for i in images]
        assert "cirros-0.6.2-x86_64" in image_names

    def test_get_image(self, openstack_connection: Connection) -> None:
        """Test getting a specific image."""
        images = list(openstack_connection.image.images())
        assert len(images) > 0

        image = openstack_connection.image.get_image(images[0].id)
        assert image is not None
        assert image.id == images[0].id

    def test_find_image_by_name(self, openstack_connection: Connection) -> None:
        """Test finding an image by name."""
        image = openstack_connection.image.find_image("cirros-0.6.2-x86_64")
        assert image is not None
        assert image.name == "cirros-0.6.2-x86_64"

    def test_create_image(self, openstack_connection: Connection) -> None:
        """Test creating a new image."""
        image = openstack_connection.image.create_image(
            name="test-sdk-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="private",
        )
        assert image is not None
        assert image.name == "test-sdk-image"
        assert image.container_format == "bare"
        assert image.disk_format == "qcow2"

    def test_update_image(self, openstack_connection: Connection) -> None:
        """Test updating an image."""
        # Create an image first
        image = openstack_connection.image.create_image(
            name="test-update-image",
            container_format="bare",
            disk_format="qcow2",
        )

        # Update it
        updated = openstack_connection.image.update_image(
            image.id,
            name="test-update-image-renamed",
        )
        assert updated.name == "test-update-image-renamed"

    def test_delete_image(self, openstack_connection: Connection) -> None:
        """Test deleting an image."""
        # Create an image first
        image = openstack_connection.image.create_image(
            name="test-delete-image",
            container_format="bare",
            disk_format="qcow2",
        )

        # Delete it
        result = openstack_connection.image.delete_image(image.id)
        assert result is None  # delete returns None on success

    def test_image_attributes(self, openstack_connection: Connection) -> None:
        """Test that images have expected attributes."""
        image = openstack_connection.image.find_image("cirros-0.6.2-x86_64")
        assert image is not None
        assert image.status is not None
        assert image.container_format is not None
        assert image.disk_format is not None


class TestGlanceImageVisibility:
    """Test Glance image visibility operations via SDK."""

    def test_create_public_image(self, openstack_connection: Connection) -> None:
        """Test creating a public image."""
        image = openstack_connection.image.create_image(
            name="test-public-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="public",
        )
        assert image is not None
        assert image.visibility == "public"

    def test_create_private_image(self, openstack_connection: Connection) -> None:
        """Test creating a private image."""
        image = openstack_connection.image.create_image(
            name="test-private-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="private",
        )
        assert image is not None
        assert image.visibility == "private"


class TestGlanceImageTags:
    """Test Glance image tag operations via SDK."""

    def test_add_tag(self, openstack_connection: Connection) -> None:
        """Test adding a tag to an image."""
        # Create an image first
        image = openstack_connection.image.create_image(
            name="test-tag-image",
            container_format="bare",
            disk_format="qcow2",
        )

        # Add a tag
        openstack_connection.image.add_tag(image.id, "test-tag")

        # Verify the tag was added
        updated = openstack_connection.image.get_image(image.id)
        assert "test-tag" in updated.tags

    def test_remove_tag(self, openstack_connection: Connection) -> None:
        """Test removing a tag from an image."""
        # Create an image with a tag
        image = openstack_connection.image.create_image(
            name="test-remove-tag-image",
            container_format="bare",
            disk_format="qcow2",
            tags=["remove-me"],
        )
        assert "remove-me" in image.tags

        # Remove the tag
        openstack_connection.image.remove_tag(image.id, "remove-me")

        # Verify the tag was removed
        updated = openstack_connection.image.get_image(image.id)
        assert "remove-me" not in updated.tags


class TestGlanceImageMembers:
    """Test Glance image member (sharing) operations via SDK."""

    def test_list_members(self, openstack_connection: Connection) -> None:
        """Test listing image members."""
        # Create a shared image
        image = openstack_connection.image.create_image(
            name="test-shared-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="shared",
        )

        # List members (should be empty initially)
        members = list(openstack_connection.image.members(image.id))
        assert isinstance(members, list)
        assert len(members) == 0

    def test_add_member(self, openstack_connection: Connection) -> None:
        """Test adding a member to an image."""
        # Create a shared image
        image = openstack_connection.image.create_image(
            name="test-add-member-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="shared",
        )

        # Add a member (using a fake project ID for testing)
        member = openstack_connection.image.add_member(
            image.id,
            member_id="fake-project-id-123",
        )
        assert member is not None
        assert member.member_id == "fake-project-id-123"
        assert member.status == "pending"

    def test_remove_member(self, openstack_connection: Connection) -> None:
        """Test removing a member from an image."""
        # Create a shared image
        image = openstack_connection.image.create_image(
            name="test-remove-member-image",
            container_format="bare",
            disk_format="qcow2",
            visibility="shared",
        )

        # Add a member
        openstack_connection.image.add_member(
            image.id,
            member_id="fake-project-id-456",
        )

        # Remove the member
        result = openstack_connection.image.remove_member(
            member="fake-project-id-456",
            image=image.id,
        )
        assert result is None  # delete returns None on success
