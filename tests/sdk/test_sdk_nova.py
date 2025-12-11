"""SDK tests for Nova Compute service."""

from openstack.connection import Connection


class TestNovaFlavors:
    """Test Nova flavor operations via SDK."""

    def test_list_flavors(self, openstack_connection: Connection) -> None:
        """Test listing flavors."""
        flavors = list(openstack_connection.compute.flavors())
        assert len(flavors) > 0

        # Default flavors should exist
        flavor_names = [f.name for f in flavors]
        assert "m1.tiny" in flavor_names
        assert "m1.small" in flavor_names

    def test_get_flavor(self, openstack_connection: Connection) -> None:
        """Test getting a specific flavor."""
        flavors = list(openstack_connection.compute.flavors())
        assert len(flavors) > 0

        flavor = openstack_connection.compute.get_flavor(flavors[0].id)
        assert flavor is not None
        assert flavor.id == flavors[0].id

    def test_find_flavor_by_name(self, openstack_connection: Connection) -> None:
        """Test finding a flavor by name."""
        flavor = openstack_connection.compute.find_flavor("m1.tiny")
        assert flavor is not None
        assert flavor.name == "m1.tiny"

    def test_flavor_attributes(self, openstack_connection: Connection) -> None:
        """Test that flavor has expected attributes."""
        flavor = openstack_connection.compute.find_flavor("m1.small")
        assert flavor is not None
        assert flavor.vcpus > 0
        assert flavor.ram > 0
        assert flavor.disk >= 0


class TestNovaServers:
    """Test Nova server (instance) operations via SDK."""

    def test_list_servers(self, openstack_connection: Connection) -> None:
        """Test listing servers (initially empty)."""
        servers = list(openstack_connection.compute.servers())
        # May be empty initially, just verify the call works
        assert isinstance(servers, list)

    def test_create_server(self, openstack_connection: Connection) -> None:
        """Test creating a server."""
        # Get a flavor and image for the server
        flavor = openstack_connection.compute.find_flavor("m1.tiny")
        assert flavor is not None

        # Use the compute proxy to list images
        images = list(openstack_connection.compute.images())
        assert len(images) > 0
        image = images[0]

        # Create server
        server = openstack_connection.compute.create_server(
            name="test-sdk-server",
            flavor_id=flavor.id,
            image_id=image.id,
        )
        assert server is not None
        assert server.name == "test-sdk-server"

    def test_get_server(self, openstack_connection: Connection) -> None:
        """Test getting a specific server."""
        # Create a server first
        flavor = openstack_connection.compute.find_flavor("m1.tiny")
        images = list(openstack_connection.compute.images())
        image = images[0]

        server = openstack_connection.compute.create_server(
            name="test-get-server",
            flavor_id=flavor.id,
            image_id=image.id,
        )

        # Get the server
        fetched = openstack_connection.compute.get_server(server.id)
        assert fetched is not None
        assert fetched.id == server.id
        assert fetched.name == "test-get-server"

    def test_delete_server(self, openstack_connection: Connection) -> None:
        """Test deleting a server."""
        # Create a server first
        flavor = openstack_connection.compute.find_flavor("m1.tiny")
        images = list(openstack_connection.compute.images())
        image = images[0]

        server = openstack_connection.compute.create_server(
            name="test-delete-server",
            flavor_id=flavor.id,
            image_id=image.id,
        )

        # Delete it
        result = openstack_connection.compute.delete_server(server.id)
        assert result is None  # delete returns None on success

    def test_server_with_keypair(self, openstack_connection: Connection) -> None:
        """Test creating a server with a keypair."""
        # Create a keypair first
        keypair = openstack_connection.compute.create_keypair(
            name="test-server-key",
        )

        # Create server with keypair
        flavor = openstack_connection.compute.find_flavor("m1.tiny")
        images = list(openstack_connection.compute.images())
        image = images[0]

        server = openstack_connection.compute.create_server(
            name="test-server-with-key",
            flavor_id=flavor.id,
            image_id=image.id,
            key_name=keypair.name,
        )
        assert server is not None
        assert server.key_name == "test-server-key"


class TestNovaKeypairs:
    """Test Nova keypair operations via SDK."""

    def test_list_keypairs(self, openstack_connection: Connection) -> None:
        """Test listing keypairs."""
        keypairs = list(openstack_connection.compute.keypairs())
        # Initially may be empty
        assert isinstance(keypairs, list)

    def test_create_keypair(self, openstack_connection: Connection) -> None:
        """Test creating a keypair (auto-generated)."""
        keypair = openstack_connection.compute.create_keypair(
            name="test-sdk-keypair",
        )
        assert keypair is not None
        assert keypair.name == "test-sdk-keypair"
        # Auto-generated keypair should have a private key
        assert keypair.private_key is not None

    def test_create_keypair_with_public_key(self, openstack_connection: Connection) -> None:
        """Test creating a keypair with provided public key."""
        public_key = (
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDJq7S7HJtvmCAuxbhV8ND"
            "HfVeRWK6dkJNrS1Vnr/fj4xYYwLbsdnlqE3JXBN7YUt+IpPq7+hSnHD7rx"
            "XVdkNe+WS7ueRlOLLXKWen+9J53LMsT3D2I test@example.com"
        )
        keypair = openstack_connection.compute.create_keypair(
            name="test-import-keypair",
            public_key=public_key,
        )
        assert keypair is not None
        assert keypair.name == "test-import-keypair"
        # Imported keypair should not have a private key
        assert keypair.private_key is None

    def test_get_keypair(self, openstack_connection: Connection) -> None:
        """Test getting a specific keypair."""
        # Create first
        keypair = openstack_connection.compute.create_keypair(
            name="test-get-keypair",
        )

        # Get it
        fetched = openstack_connection.compute.get_keypair(keypair.name)
        assert fetched is not None
        assert fetched.name == "test-get-keypair"

    def test_delete_keypair(self, openstack_connection: Connection) -> None:
        """Test deleting a keypair."""
        # Create first
        keypair = openstack_connection.compute.create_keypair(
            name="test-delete-keypair",
        )

        # Delete it
        result = openstack_connection.compute.delete_keypair(keypair.name)
        assert result is None  # delete returns None on success


class TestNovaImages:
    """Test Nova image operations via SDK (deprecated, prefer Glance)."""

    def test_list_images(self, openstack_connection: Connection) -> None:
        """Test listing images via compute API."""
        images = list(openstack_connection.compute.images())
        assert len(images) > 0

    def test_get_image(self, openstack_connection: Connection) -> None:
        """Test getting a specific image."""
        images = list(openstack_connection.compute.images())
        assert len(images) > 0

        image = openstack_connection.compute.get_image(images[0].id)
        assert image is not None


class TestNovaAvailabilityZones:
    """Test Nova availability zone operations via SDK."""

    def test_list_availability_zones(self, openstack_connection: Connection) -> None:
        """Test listing availability zones."""
        zones = list(openstack_connection.compute.availability_zones())
        assert len(zones) > 0

        # Should have nova zone
        zone_names = [z.name for z in zones]
        assert "nova" in zone_names
