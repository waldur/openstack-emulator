import json
import os
import tempfile
import unittest

from emulator.core import persistence
from emulator.core.database import Database
from emulator.core.presets.loader import PresetLoader


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.json")
        self.db = Database(persist_path=self.db_path)
        # Enable auto-save for testing
        self.db.auto_save = True

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_server(self):
        # Create a server
        server = self.db.create_server(
            name="test-server", flavor_id="m1.tiny", image_id="cirros", tenant_id="p1", user_id="u1"
        )
        server_id = server.id

        # Verify file exists (auto-save enabled)
        self.assertTrue(os.path.exists(self.db_path))

        # Create a new database instance loading from the same path
        new_db = Database(persist_path=self.db_path)
        new_db.load()

        # Verify server exists in new db
        loaded_server = new_db.get_server(server_id)
        self.assertIsNotNone(loaded_server)
        self.assertEqual(loaded_server.name, "test-server")
        self.assertEqual(loaded_server.tenant_id, "p1")
        self.assertEqual(loaded_server.status, server.status)

    def test_save_and_load_flavor(self):
        self.db.create_flavor(
            name="test-flavor", vcpus=2, ram=2048, disk=20, flavor_id="test-flavor-id"
        )

        new_db = Database(persist_path=self.db_path)
        new_db.load()

        loaded_flavor = new_db.get_flavor("test-flavor-id")
        self.assertIsNotNone(loaded_flavor)
        self.assertEqual(loaded_flavor.vcpus, 2)
        self.assertEqual(loaded_flavor.ram, 2048)

    def test_save_and_load_image(self):
        image = self.db.create_image(name="test-image", min_disk=10, min_ram=512, size=1073741824)
        image_id = image.id

        new_db = Database(persist_path=self.db_path)
        new_db.load()

        loaded_image = new_db.get_image(image_id)
        self.assertIsNotNone(loaded_image)
        self.assertEqual(loaded_image.name, "test-image")
        self.assertEqual(loaded_image.min_disk, 10)

    def test_save_and_load_keypair(self):
        self.db.create_keypair(name="test-key", user_id="test-user", public_key="ssh-rsa AAA...")

        new_db = Database(persist_path=self.db_path)
        new_db.load()

        loaded_kp = new_db.get_keypair("test-key", "test-user")
        self.assertIsNotNone(loaded_kp)
        self.assertEqual(loaded_kp.public_key, "ssh-rsa AAA...")

    def test_auto_save_on_delete(self):
        server = self.db.create_server(
            name="to-delete", flavor_id="m1.tiny", image_id="cirros", tenant_id="p1", user_id="u1"
        )
        server_id = server.id

        self.assertTrue(os.path.exists(self.db_path))

        # Verify it's in the file
        with open(self.db_path) as f:
            data = json.load(f)
            self.assertIn(server_id, data["servers"])

        # Delete server
        self.db.delete_server(server_id)

        # Verify it's removed from file
        with open(self.db_path) as f:
            data = json.load(f)
            self.assertNotIn(server_id, data["servers"])

    def test_persistence_all_resources(self):
        # Create one of everything
        net = self.db.create_network("test-net", "p1")
        subnet = self.db.create_subnet(net.id, "10.0.0.0/24", "p1")
        vol = self.db.create_volume("test-vol", 10, "p1", "u1")

        new_db = Database(persist_path=self.db_path)
        new_db.load()

        self.assertIsNotNone(new_db.get_network(net.id))
        self.assertIsNotNone(new_db.get_subnet(subnet.id))
        self.assertIsNotNone(new_db.get_volume(vol.id))

    def test_reloaded_neutron_resources_serialize(self):
        """Statuses must survive a reload as enums, not bare strings.

        A bare string reaches ``to_dict()`` as ``self.status.value`` and blows
        up with AttributeError on the first list call after a restart.
        """
        net = self.db.create_network("test-net", "p1")
        port = self.db.create_port(network_id=net.id, project_id="p1", name="test-port")
        router = self.db.create_router(name="test-router", project_id="p1")

        new_db = Database(persist_path=self.db_path)
        new_db.load()

        self.assertEqual(new_db.get_network(net.id).to_dict()["status"], "ACTIVE")
        self.assertEqual(new_db.get_port(port.id).to_dict()["status"], "ACTIVE")
        self.assertEqual(new_db.get_router(router.id).to_dict()["status"], "ACTIVE")

    def test_load_nonexistent_file(self):
        # Should initiate with defaults if file doesn't exist
        db = Database(persist_path="nonexistent.json")
        db.load()
        # Check defaults are present
        self.assertTrue(len(db._flavors) > 0)
        self.assertTrue(any(f.name == "m1.tiny" for f in db._flavors.values()))


class TestRegistryCoverage(unittest.TestCase):
    """The registry is what keeps the round trip honest.

    Persistence used to cover 17 of ~75 collections, and nothing said so. A new
    collection now has to be declared persisted or explicitly excluded, or this
    fails.
    """

    def test_every_database_attribute_is_classified(self):
        db = Database()
        classified = (
            {c.attr for c in persistence.PERSISTED}
            | set(persistence.PERSISTED_SCALARS)
            | set(persistence.NOT_PERSISTED)
        )
        attributes = {name for name in vars(db) if name.startswith("_")}
        unclassified = sorted(attributes - classified)
        self.assertEqual(
            unclassified,
            [],
            f"add {unclassified} to PERSISTED, PERSISTED_SCALARS or NOT_PERSISTED "
            "in emulator/core/persistence.py",
        )

    def test_registry_does_not_reference_missing_attributes(self):
        db = Database()
        for collection in persistence.PERSISTED:
            self.assertTrue(hasattr(db, collection.attr), f"no such attribute {collection.attr}")
        for name in persistence.PERSISTED_SCALARS:
            self.assertTrue(hasattr(db, name), f"no such attribute {name}")

    def test_collection_keys_are_unique(self):
        keys = [c.key for c in persistence.PERSISTED]
        self.assertEqual(len(keys), len(set(keys)))
        # "scalars" and "schema_version" are reserved for the envelope.
        self.assertNotIn("scalars", keys)
        self.assertNotIn("schema_version", keys)


class TestFullRoundTrip(unittest.TestCase):
    """Save and load a richly populated database and compare it field by field."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "db.json")
        self.db = Database(persist_path=self.db_path)
        PresetLoader(self.db).load_preset_by_name("production")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _reload(self):
        self.db.save()
        reloaded = Database(persist_path=self.db_path)
        reloaded.load()
        self.assertFalse(reloaded._load_degraded, "load reported dropped records")
        return reloaded

    def test_preset_state_round_trips(self):
        reloaded = self._reload()
        populated = 0
        for collection in persistence.PERSISTED:
            before = getattr(self.db, collection.attr)
            after = getattr(reloaded, collection.attr)
            if collection.attr == "_images":
                # Nova's image list is a projection of Glance rebuilt on load,
                # so it can legitimately gain entries for Glance images that
                # were never mirrored into it. Every saved image must survive.
                self.assertLessEqual(before.items(), after.items())
            else:
                self.assertEqual(after, before, f"{collection.key} did not round-trip")
            if before:
                populated += 1
        # Guard against the comparison passing because everything was empty.
        self.assertGreater(populated, 10)

    def test_scalars_round_trip(self):
        reloaded = self._reload()
        for name in persistence.PERSISTED_SCALARS:
            self.assertEqual(getattr(reloaded, name), getattr(self.db, name), name)

    def test_to_dict_works_for_every_reloaded_object(self):
        """The regression sweep for the production crash.

        ``Network.to_dict()`` raised ``AttributeError: 'str' object has no
        attribute 'value'`` after a restart because the status enum came back as
        a plain string. Calling it on everything catches the whole family.
        """
        reloaded = self._reload()
        checked = 0
        for collection in persistence.PERSISTED:
            value = getattr(reloaded, collection.attr)
            for obj in self._iter_models(collection, value):
                if hasattr(obj, "to_dict"):
                    obj.to_dict()
                    checked += 1
        self.assertGreater(checked, 10)

    @staticmethod
    def _iter_models(collection, value):
        if collection.shape is persistence.Shape.DATACLASS:
            yield value
        elif collection.shape is persistence.Shape.LIST:
            yield from value
        elif collection.shape is persistence.Shape.DICT_OF_LIST:
            for bucket in value.values():
                yield from bucket
        elif collection.shape is persistence.Shape.DICT:
            yield from value.values()


class TestDataLossRegressions(unittest.TestCase):
    """Each of these lost user state on every restart."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "db.json")
        self.db = Database(persist_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _reload(self):
        self.db.save()
        reloaded = Database(persist_path=self.db_path)
        reloaded.load()
        return reloaded

    def test_security_group_rules_survive(self):
        sg = self.db.get_or_create_default_security_group("p1")
        rule = self.db.create_security_group_rule(
            security_group_id=sg.id, project_id="p1", direction="ingress", protocol="tcp"
        )

        reloaded = self._reload()

        loaded_sg = reloaded.get_security_group(sg.id)
        self.assertEqual(len(loaded_sg.security_group_rules), len(sg.security_group_rules))
        self.assertIn(rule.id, {r.id for r in loaded_sg.security_group_rules})
        self.assertIn(rule.id, reloaded._security_group_rules)

    def test_default_security_group_is_saved_when_auto_save_is_on(self):
        self.db.auto_save = True
        sg = self.db.get_or_create_default_security_group("p1")

        reloaded = Database(persist_path=self.db_path)
        reloaded.load()

        self.assertIsNotNone(reloaded.get_security_group(sg.id))

    def test_attached_volume_can_still_be_detached(self):
        """The volume used to come back in-use with no attachment: stuck forever."""
        server = self.db.create_server(
            name="s1", flavor_id="1", image_id="cirros", tenant_id="p1", user_id="u1"
        )
        volume = self.db.create_volume("v1", 10, "p1", "u1")
        attachment = self.db.attach_volume_to_server(server.id, volume.id)

        reloaded = self._reload()

        loaded = reloaded.list_server_volume_attachments(server.id)
        self.assertEqual([a.attachment_id for a in loaded], [attachment.attachment_id])
        self.assertTrue(reloaded.detach_volume_from_server(server.id, attachment.attachment_id))

    def test_floating_ip_addresses_are_not_reused_after_restart(self):
        external = self.db.create_network("ext", "p1", external=True)
        self.db.create_subnet(external.id, "203.0.113.0/24", "p1")
        first = self.db.create_floating_ip(external.id, "p1")

        reloaded = self._reload()
        second = reloaded.create_floating_ip(external.id, "p1")

        self.assertNotEqual(first.floating_ip_address, second.floating_ip_address)

    def test_network_keeps_its_subnets(self):
        network = self.db.create_network("n1", "p1")
        subnet = self.db.create_subnet(network.id, "10.0.0.0/24", "p1")

        reloaded = self._reload()

        self.assertEqual(reloaded.get_network(network.id).subnets, [subnet.id])
        self.assertEqual(reloaded.get_network(network.id).to_dict()["subnets"], [subnet.id])

    def test_router_keeps_static_routes(self):
        router = self.db.create_router(name="r1", project_id="p1")
        router.routes = [{"destination": "10.10.0.0/24", "nexthop": "10.0.0.1"}]

        reloaded = self._reload()

        self.assertEqual(reloaded.get_router(router.id).routes, router.routes)

    def test_server_delete_still_releases_ports_after_restart(self):
        """delete_server frees ports via _server_network_interfaces, which was dropped."""
        network = self.db.create_network("n1", "p1")
        port = self.db.create_port(network_id=network.id, project_id="p1")
        server = self.db.create_server(
            name="s1", flavor_id="1", image_id="cirros", tenant_id="p1", user_id="u1"
        )
        self.db.attach_interface_to_server(server.id, port)

        reloaded = self._reload()
        reloaded.delete_server(server.id)

        self.assertEqual(reloaded.get_port(port.id).device_id, "")

    def test_keystone_defaults_still_point_at_real_objects(self):
        """The default ids were re-minted on boot while the objects were loaded."""
        reloaded = self._reload()

        self.assertIsNotNone(reloaded.get_project(reloaded._default_project_id))
        self.assertIsNotNone(reloaded.get_user(reloaded._default_user_id))
        self.assertIn(reloaded._admin_role_id, reloaded._roles)

    def test_quotas_survive(self):
        self.db.update_nova_quota("p1", cores=42)

        reloaded = self._reload()

        self.assertEqual(reloaded.get_nova_quota("p1").cores, 42)


class TestLegacyFormat(unittest.TestCase):
    """Files written before schema versioning must still load, then upgrade."""

    #: Shaped like the file the deployed 0.2.3 wrote: no schema_version,
    #: API-style keys ("tenant_id", "router:external") and a bare-string status.
    V1_FILE = {
        "networks": {
            "net-1": {
                "id": "net-1",
                "name": "prod-net",
                "description": "",
                "tenant_id": "tenant-1",
                "project_id": "tenant-1",
                "admin_state_up": True,
                "status": "ACTIVE",
                "shared": False,
                "router:external": False,
                "mtu": 1500,
                "port_security_enabled": True,
                "provider:network_type": None,
                "provider:physical_network": None,
                "provider:segmentation_id": None,
                "created_at": "2026-07-01T10:00:00",
                "updated_at": "2026-07-01T10:00:00",
            }
        }
    }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "db.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, payload):
        with open(self.db_path, "w") as f:
            json.dump(payload, f)

    def test_v1_file_loads_and_serializes(self):
        self._write(self.V1_FILE)

        db = Database(persist_path=self.db_path)
        db.load()

        network = db.get_network("net-1")
        self.assertEqual(network.name, "prod-net")
        # The production crash: this raised AttributeError on a bare string.
        self.assertEqual(network.to_dict()["status"], "ACTIVE")
        self.assertFalse(db._load_degraded)

    def test_saving_upgrades_a_v1_file(self):
        self._write(self.V1_FILE)

        db = Database(persist_path=self.db_path)
        db.load()
        db.save()

        with open(self.db_path) as f:
            upgraded = json.load(f)
        self.assertEqual(upgraded["schema_version"], persistence.SCHEMA_VERSION)

        reloaded = Database(persist_path=self.db_path)
        reloaded.load()
        self.assertEqual(reloaded.get_network("net-1").to_dict()["status"], "ACTIVE")
        self.assertFalse(reloaded._load_degraded)


class TestDamagedFile(unittest.TestCase):
    """A file we cannot fully read must not be silently replaced."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "db.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _corrupt_file(self):
        db = Database(persist_path=self.db_path)
        good = db.create_network("keep-me", "p1")
        db.save()
        with open(self.db_path) as f:
            data = json.load(f)
        # "SHRUG" is not a NetworkStatus, so decoding this record raises.
        data["networks"]["broken"] = {"id": "broken", "name": "bad", "status": "SHRUG"}
        with open(self.db_path, "w") as f:
            json.dump(data, f)
        return good.id

    def test_one_bad_record_does_not_discard_the_rest(self):
        good_id = self._corrupt_file()

        db = Database(persist_path=self.db_path)
        db.load()

        self.assertIsNotNone(db.get_network(good_id))
        self.assertIsNone(db.get_network("broken"))
        self.assertTrue(db._load_degraded)
        # Collections decoded after the bad one must still be present.
        self.assertTrue(db._flavors)

    def test_original_is_preserved_before_being_overwritten(self):
        self._corrupt_file()

        db = Database(persist_path=self.db_path)
        db.load()
        db.save()

        backups = [n for n in os.listdir(self.temp_dir.name) if ".corrupt-" in n]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.temp_dir.name, backups[0])) as f:
            self.assertIn("broken", json.load(f)["networks"])

    def test_unreadable_json_leaves_defaults_intact(self):
        with open(self.db_path, "w") as f:
            f.write("{not json")

        db = Database(persist_path=self.db_path)
        db.load()

        self.assertTrue(db._load_degraded)
        self.assertTrue(any(f.name == "m1.tiny" for f in db._flavors.values()))

    def test_save_is_atomic(self):
        db = Database(persist_path=self.db_path)
        db.create_network("n1", "p1")
        db.save()

        leftovers = [n for n in os.listdir(self.temp_dir.name) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
