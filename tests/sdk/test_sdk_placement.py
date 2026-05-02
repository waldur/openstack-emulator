"""SDK tests for the Placement service."""

from openstack.connection import Connection

from emulator.core.database import db


class TestPlacementResourceProviders:
    def test_list_resource_providers(self, openstack_connection: Connection) -> None:
        providers = list(openstack_connection.placement.resource_providers())
        assert len(providers) == 1
        assert providers[0].name == "compute-host-1"

    def test_get_resource_provider_by_uuid(self, openstack_connection: Connection) -> None:
        seeded = db.list_resource_providers()[0]
        fetched = openstack_connection.placement.get_resource_provider(seeded.uuid)
        assert fetched.id == seeded.uuid
        assert fetched.name == "compute-host-1"

    def test_find_resource_provider_by_name(self, openstack_connection: Connection) -> None:
        provider = openstack_connection.placement.find_resource_provider("compute-host-1")
        assert provider is not None
        assert provider.name == "compute-host-1"


class TestPlacementInventoriesAndUsages:
    def test_inventories_have_standard_resource_classes(
        self, openstack_connection: Connection
    ) -> None:
        seeded = db.list_resource_providers()[0]
        # The SDK's inventory accessor returns one inventory per resource class.
        inventories = list(
            openstack_connection.placement.resource_provider_inventories(seeded.uuid)
        )
        classes = {inv.resource_class for inv in inventories}
        assert {"VCPU", "MEMORY_MB", "DISK_GB"} <= classes
        for inv in inventories:
            assert inv.total > 0
            assert inv.allocation_ratio >= 1.0

    def test_usages_track_running_servers(self, openstack_connection: Connection) -> None:
        # Placement usages should reflect a server created via the compute API.
        flavor = openstack_connection.compute.find_flavor("m1.small")
        assert flavor is not None
        images = list(openstack_connection.compute.images())
        assert images, "expected at least one image to be available"

        openstack_connection.compute.create_server(
            name="placement-usage-vm",
            flavor_id=flavor.id,
            image_id=images[0].id,
        )

        seeded = db.list_resource_providers()[0]
        usages = db.get_resource_provider_usages(seeded.uuid)
        assert usages is not None
        assert usages["usages"]["VCPU"] == flavor.vcpus
        assert usages["usages"]["MEMORY_MB"] == flavor.ram
        assert usages["usages"]["DISK_GB"] == flavor.disk
