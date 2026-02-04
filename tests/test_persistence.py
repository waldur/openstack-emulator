import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from emulator.core.database import Database
from emulator.core.models import Server, Flavor, Image, ServerStatus, PowerState


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
        flavor = self.db.create_flavor(
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
        kp = self.db.create_keypair(
            name="test-key", user_id="test-user", public_key="ssh-rsa AAA..."
        )

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

    def test_load_nonexistent_file(self):
        # Should initiate with defaults if file doesn't exist
        db = Database(persist_path="nonexistent.json")
        db.load()
        # Check defaults are present
        self.assertTrue(len(db._flavors) > 0)
        self.assertTrue(any(f.name == "m1.tiny" for f in db._flavors.values()))


if __name__ == "__main__":
    unittest.main()
