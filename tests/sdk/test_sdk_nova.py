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


class TestNovaServerActions:
    """Test Nova server action operations via SDK."""

    def _create_test_server(self, conn: Connection, name: str = "test-action-server") -> object:
        """Helper to create a test server."""
        flavor = conn.compute.find_flavor("m1.tiny")
        images = list(conn.compute.images())
        image = images[0]
        server = conn.compute.create_server(
            name=name,
            flavor_id=flavor.id,
            image_id=image.id,
        )
        # Wait for the server to become ACTIVE
        server = conn.compute.wait_for_server(server, status="ACTIVE", wait=30)
        return server

    def test_server_stop_and_start(self, openstack_connection: Connection) -> None:
        """Test stopping and starting a server."""
        server = self._create_test_server(openstack_connection, "test-stop-start")

        # Stop the server
        openstack_connection.compute.stop_server(server)
        server = openstack_connection.compute.wait_for_server(server, status="SHUTOFF", wait=30)
        assert server.status == "SHUTOFF"

        # Start the server
        openstack_connection.compute.start_server(server)
        server = openstack_connection.compute.wait_for_server(server, status="ACTIVE", wait=30)
        assert server.status == "ACTIVE"

    def test_server_reboot(self, openstack_connection: Connection) -> None:
        """Test rebooting a server."""
        server = self._create_test_server(openstack_connection, "test-reboot")

        # Reboot the server (soft reboot)
        openstack_connection.compute.reboot_server(server, reboot_type="SOFT")
        server = openstack_connection.compute.wait_for_server(server, status="ACTIVE", wait=30)
        assert server.status == "ACTIVE"

    def test_server_resize_and_confirm(self, openstack_connection: Connection) -> None:
        """Test resizing a server and confirming the resize."""
        server = self._create_test_server(openstack_connection, "test-resize-confirm")

        # Get original flavor
        original_flavor = openstack_connection.compute.find_flavor("m1.tiny")
        assert server.flavor["id"] == original_flavor.id

        # Get a different flavor to resize to
        new_flavor = openstack_connection.compute.find_flavor("m1.small")
        assert new_flavor is not None
        assert new_flavor.id != original_flavor.id

        # Resize the server
        openstack_connection.compute.resize_server(server, new_flavor.id)

        # Wait for VERIFY_RESIZE status
        server = openstack_connection.compute.wait_for_server(
            server, status="VERIFY_RESIZE", wait=30
        )
        assert server.status == "VERIFY_RESIZE"

        # Confirm the resize
        openstack_connection.compute.confirm_server_resize(server)

        # Wait for ACTIVE status after confirm
        server = openstack_connection.compute.wait_for_server(server, status="ACTIVE", wait=30)
        assert server.status == "ACTIVE"

        # Verify the flavor changed
        server = openstack_connection.compute.get_server(server.id)
        assert server.flavor["id"] == new_flavor.id

    def test_server_resize_and_revert(self, openstack_connection: Connection) -> None:
        """Test resizing a server and reverting the resize."""
        server = self._create_test_server(openstack_connection, "test-resize-revert")

        # Get original flavor
        original_flavor = openstack_connection.compute.find_flavor("m1.tiny")
        assert server.flavor["id"] == original_flavor.id

        # Get a different flavor to resize to
        new_flavor = openstack_connection.compute.find_flavor("m1.small")
        assert new_flavor is not None

        # Resize the server
        openstack_connection.compute.resize_server(server, new_flavor.id)

        # Wait for VERIFY_RESIZE status
        server = openstack_connection.compute.wait_for_server(
            server, status="VERIFY_RESIZE", wait=30
        )
        assert server.status == "VERIFY_RESIZE"

        # Revert the resize
        openstack_connection.compute.revert_server_resize(server)

        # Wait for ACTIVE status after revert
        server = openstack_connection.compute.wait_for_server(server, status="ACTIVE", wait=30)
        assert server.status == "ACTIVE"

        # Verify the flavor is back to original
        server = openstack_connection.compute.get_server(server.id)
        assert server.flavor["id"] == original_flavor.id

    def test_server_resize_from_shutoff(self, openstack_connection: Connection) -> None:
        """Test resizing a server that is in SHUTOFF state."""
        server = self._create_test_server(openstack_connection, "test-resize-shutoff")

        # Stop the server first
        openstack_connection.compute.stop_server(server)
        server = openstack_connection.compute.wait_for_server(server, status="SHUTOFF", wait=30)
        assert server.status == "SHUTOFF"

        # Get a different flavor to resize to
        new_flavor = openstack_connection.compute.find_flavor("m1.small")

        # Resize the server
        openstack_connection.compute.resize_server(server, new_flavor.id)

        # Wait for VERIFY_RESIZE status
        server = openstack_connection.compute.wait_for_server(
            server, status="VERIFY_RESIZE", wait=30
        )
        assert server.status == "VERIFY_RESIZE"

        # Confirm the resize
        openstack_connection.compute.confirm_server_resize(server)

        # After confirm, server should go back to SHUTOFF (its pre-resize state)
        server = openstack_connection.compute.wait_for_server(server, status="SHUTOFF", wait=30)
        assert server.status == "SHUTOFF"

    def test_create_server_image(self, openstack_connection: Connection) -> None:
        """Test creating a snapshot image from a server."""
        server = self._create_test_server(openstack_connection, "test-create-image")

        # Create an image from the server
        image_name = "test-server-snapshot"
        metadata = {"description": "Test snapshot", "created_by": "sdk_test"}

        # Use the compute proxy to create the image
        image_id = openstack_connection.compute.create_server_image(
            server, image_name, metadata=metadata
        )
        assert image_id is not None

        # Verify the image was created in Glance
        image = openstack_connection.image.get_image(image_id)
        assert image is not None
        assert image.name == image_name
        assert image.status == "active"

        # Check image properties (stored in properties dict)
        assert image.properties.get("image_type") == "snapshot"
        # instance_uuid is a top-level attribute, not in properties
        assert image.instance_uuid == server.id

    def test_create_server_image_with_metadata(self, openstack_connection: Connection) -> None:
        """Test creating a snapshot image with custom metadata."""
        server = self._create_test_server(openstack_connection, "test-image-metadata")

        # Create an image with custom metadata
        image_name = "test-snapshot-with-metadata"
        metadata = {
            "backup_type": "daily",
            "retention_days": "7",
        }

        image_id = openstack_connection.compute.create_server_image(
            server, image_name, metadata=metadata
        )
        assert image_id is not None

        # Verify the metadata was applied (in properties dict)
        image = openstack_connection.image.get_image(image_id)
        assert image is not None
        assert image.properties.get("backup_type") == "daily"
        assert image.properties.get("retention_days") == "7"

    def test_get_server_console_output(self, openstack_connection: Connection) -> None:
        """Test getting console output from a server."""
        server = self._create_test_server(openstack_connection, "test-console-output")

        # Get console output
        output = openstack_connection.compute.get_server_console_output(server)
        assert output is not None
        # The emulator returns a stub message
        assert isinstance(output, dict)
        assert "output" in output


class TestSDKServerPortBinding:
    """Booting a server binds its port, as Nova does.

    This is the contract a client relies on to find an instance's ports:
    ``allocate_for_instance`` stamps ``device_id`` with the server uuid and
    ``device_owner`` with ``compute:<availability zone>``, so the port turns up
    under a ``device_id`` filter and under ``os-interface``.
    """

    def _network(self, conn, cidr="192.168.77.0/24"):
        net = conn.network.create_network(name="bind-net")
        conn.network.create_subnet(name="bind-sub", network_id=net.id, ip_version=4, cidr=cidr)
        return net

    def test_boot_with_a_port_binds_it(self, openstack_connection: Connection) -> None:
        net = self._network(openstack_connection)
        port = openstack_connection.network.create_port(network_id=net.id)
        image = next(iter(openstack_connection.image.images()))
        flavor = openstack_connection.compute.find_flavor("m1.small")

        server = openstack_connection.compute.create_server(
            name="bound-vm",
            flavor_id=flavor.id,
            image_id=image.id,
            networks=[{"port": port.id}],
        )

        refetched = openstack_connection.network.get_port(port.id)
        assert refetched.device_id == server.id
        assert refetched.device_owner == "compute:nova"

    def test_the_port_is_discoverable_the_way_nova_finds_it(
        self, openstack_connection: Connection
    ) -> None:
        net = self._network(openstack_connection, cidr="192.168.78.0/24")
        port = openstack_connection.network.create_port(network_id=net.id)
        image = next(iter(openstack_connection.image.images()))
        flavor = openstack_connection.compute.find_flavor("m1.small")

        server = openstack_connection.compute.create_server(
            name="findable-vm",
            flavor_id=flavor.id,
            image_id=image.id,
            networks=[{"port": port.id}],
        )

        by_device = list(openstack_connection.network.ports(device_id=server.id))
        assert [p.id for p in by_device] == [port.id]

        interfaces = list(openstack_connection.compute.server_interfaces(server.id))
        assert [i.port_id for i in interfaces] == [port.id]

    def test_boot_with_a_network_creates_and_binds_a_port(
        self, openstack_connection: Connection
    ) -> None:
        net = self._network(openstack_connection, cidr="192.168.79.0/24")
        image = next(iter(openstack_connection.image.images()))
        flavor = openstack_connection.compute.find_flavor("m1.small")

        server = openstack_connection.compute.create_server(
            name="auto-port-vm",
            flavor_id=flavor.id,
            image_id=image.id,
            networks=[{"uuid": net.id}],
        )

        by_device = list(openstack_connection.network.ports(device_id=server.id))
        assert len(by_device) == 1
        assert by_device[0].network_id == net.id

    def test_a_port_carries_an_allocated_address(self, openstack_connection: Connection) -> None:
        """A port on a subnet gets an IP, so addresses are real rather than blank."""
        net = self._network(openstack_connection, cidr="192.168.80.0/24")

        port = openstack_connection.network.create_port(network_id=net.id)

        assert port.fixed_ips
        assert port.fixed_ips[0]["ip_address"].startswith("192.168.80.")
        # The gateway is not handed out.
        assert port.fixed_ips[0]["ip_address"] != "192.168.80.1"


class TestNovaServerMetadata:
    """Server metadata through a real SDK client.

    Waldur drives this sub-resource the way novaclient does: a merging POST to
    set keys and a DELETE per key to drop them. The SDK's
    ``set_server_metadata`` / ``delete_server_metadata`` hit the same two
    endpoints, so these exercise the wire contract those clients depend on.
    """

    def _server(self, conn: Connection, name: str, metadata: dict[str, str] | None = None):
        flavor = conn.compute.find_flavor("m1.tiny")
        assert flavor is not None
        image = list(conn.compute.images())[0]
        return conn.compute.create_server(
            name=name,
            flavor_id=flavor.id,
            image_id=image.id,
            metadata=metadata or {},
        )

    def test_metadata_given_at_boot_round_trips(self, openstack_connection: Connection) -> None:
        server = self._server(openstack_connection, "meta-boot", {"env": "prod", "role": "db"})

        fetched = openstack_connection.compute.get_server(server.id)
        assert fetched.metadata == {"env": "prod", "role": "db"}

    def test_set_metadata_merges(self, openstack_connection: Connection) -> None:
        server = self._server(
            openstack_connection, "meta-merge", {"env": "staging", "owner": "team-a"}
        )

        openstack_connection.compute.set_server_metadata(server, env="prod", role="db")

        metadata = openstack_connection.compute.fetch_server_metadata(server).metadata
        assert metadata == {"env": "prod", "owner": "team-a", "role": "db"}

    def test_delete_metadata_removes_only_the_named_keys(
        self, openstack_connection: Connection
    ) -> None:
        server = self._server(
            openstack_connection, "meta-delete", {"env": "prod", "owner": "team-a"}
        )

        openstack_connection.compute.delete_server_metadata(server, ["owner"])

        metadata = openstack_connection.compute.fetch_server_metadata(server).metadata
        assert metadata == {"env": "prod"}

    def test_replacing_metadata_takes_a_delete_then_a_set(
        self, openstack_connection: Connection
    ) -> None:
        # The sequence Waldur's push performs: prune what disappeared, then push
        # the new pairs. Doing it in this order also keeps the intermediate state
        # from exceeding the metadata_items quota.
        server = self._server(
            openstack_connection, "meta-replace", {"env": "staging", "owner": "team-a"}
        )

        openstack_connection.compute.delete_server_metadata(server, ["owner"])
        openstack_connection.compute.set_server_metadata(server, env="prod")

        metadata = openstack_connection.compute.fetch_server_metadata(server).metadata
        assert metadata == {"env": "prod"}
