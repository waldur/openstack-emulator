"""Two gaps found by running a real site agent against the emulator.

1. Nova serves images from its own store. The seeded images are written to both
   stores, but ``create_glance_image`` only wrote the Glance one, so an image
   uploaded through the API — or seeded by a preset — could be listed in Glance
   and still be rejected by Nova with "Image not found". A preset that seeds an
   image *and* a server using it produced exactly that contradiction.

2. Deleting a server left its volumes carrying an attachment to an instance that
   no longer existed. The volume stayed ``in-use`` forever: it could not be
   deleted, re-attached, or reasoned about by anything that walks attachments.
"""

import pytest

from emulator.core.database import Database
from emulator.core.models import ImageVisibility, VolumeStatus


@pytest.fixture
def db():
    return Database()


@pytest.fixture
def project(db):
    return db.create_project(name="tenant", domain_id="default").id


class TestGlanceImagesAreBootable:
    """An image that Glance lists must be an image Nova can boot."""

    def test_a_created_image_appears_in_nova(self, db, project):
        image = db.create_glance_image(
            name="custom", owner=project, visibility=ImageVisibility.PUBLIC
        )

        assert db.get_image(image.id) is not None
        assert image.id in {i.id for i in db.list_images()}

    def test_a_created_image_can_be_booted(self, db, project):
        image = db.create_glance_image(name="custom", owner=project)

        server = db.create_server(name="vm", image_id=image.id, flavor_id="1", tenant_id=project)

        assert server is not None

    def test_deleting_the_image_removes_it_from_nova_too(self, db, project):
        image = db.create_glance_image(name="custom", owner=project)

        db.delete_glance_image(image.id)

        assert db.get_image(image.id) is None


class TestServerDeleteReleasesVolumes:
    """A deleted server must not leave its volumes pinned to it."""

    @pytest.fixture
    def attached(self, db, project):
        server = db.create_server(
            name="vm",
            image_id=next(iter(db.list_glance_images())).id,
            flavor_id="1",
            tenant_id=project,
        )
        volume = db.create_volume(name="vol", size=10, project_id=project, user_id="u1")
        db.attach_volume_to_server(server.id, volume.id)
        db.attach_volume(volume.id, server.id)
        return server, db.get_volume(volume.id)

    def test_the_volume_is_detached(self, db, attached):
        server, volume = attached

        db.delete_server(server.id)

        assert db.get_volume(volume.id).attachments == []

    def test_the_volume_becomes_available_again(self, db, attached):
        server, volume = attached

        db.delete_server(server.id)

        assert db.get_volume(volume.id).status == VolumeStatus.AVAILABLE

    def test_no_attachment_survives_pointing_at_a_dead_server(self, db, attached):
        """The failure mode: an attachment naming an instance that is gone."""
        server, volume = attached

        db.delete_server(server.id)

        live = {s.id for s in db.list_servers()}
        for attachment in db.get_volume(volume.id).attachments:
            assert attachment.server_id in live

    def test_delete_on_termination_takes_the_volume_with_it(self, db, project):
        server = db.create_server(
            name="vm",
            image_id=next(iter(db.list_glance_images())).id,
            flavor_id="1",
            tenant_id=project,
        )
        volume = db.create_volume(name="vol", size=10, project_id=project, user_id="u1")
        db.attach_volume_to_server(server.id, volume.id, delete_on_termination=True)
        db.attach_volume(volume.id, server.id)

        db.delete_server(server.id)

        assert db.get_volume(volume.id) is None
