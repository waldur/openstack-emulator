"""SDK tests for Swift object storage against the emulator."""

from openstack.connection import Connection


class TestSDKSwiftAccount:
    """Account metadata and usage through the SDK."""

    def test_get_account_metadata(self, openstack_connection: Connection) -> None:
        account = openstack_connection.object_store.get_account_metadata()

        assert account.account_container_count == 0
        assert account.account_object_count == 0
        assert account.account_bytes_used == 0

    def test_set_account_metadata(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.set_account_metadata(**{"owner": "waldur"})

        account = openstack_connection.object_store.get_account_metadata()
        assert account.metadata["owner"] == "waldur"

    def test_account_usage_tracks_uploads(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.create_container(name="docs")
        openstack_connection.object_store.upload_object(
            container="docs", name="a.txt", data=b"hello"
        )

        account = openstack_connection.object_store.get_account_metadata()
        assert account.account_container_count == 1
        assert account.account_object_count == 1
        assert account.account_bytes_used == 5


class TestSDKSwiftQuota:
    """The account quota header a client would use to cap a project."""

    def test_quota_is_set_on_the_account_in_the_storage_url(
        self, openstack_connection: Connection, admin_project_id: str
    ) -> None:
        """set_account_metadata targets the catalog account, nothing else.

        The SDK signature is ``set_account_metadata(**metadata)`` — there is no
        account parameter. The account acted on is always the one embedded in the
        object-store endpoint, so a caller wanting to set a quota on some *other*
        project's account cannot do it through this call: passing ``account=...``
        merely stores a metadata key named "account". This is pinned because it
        is an easy and silent mistake to make.
        """
        from emulator.core.database import db

        openstack_connection.object_store.set_account_metadata(
            **{"quota-bytes": "1000", "account": "some-other-project"}
        )

        own_account = db.get_swift_account(f"AUTH_{admin_project_id}", create=False)
        assert own_account is not None
        # The quota landed on the caller's own account...
        assert own_account.sysmeta.get("quota-bytes") == "1000"
        # ...and "account" was taken as an ordinary metadata key, not a target.
        assert own_account.metadata.get("account") == "some-other-project"
        assert db.get_swift_account("AUTH_some-other-project", create=False) is None

    def test_quota_does_not_come_back_as_user_metadata(
        self, openstack_connection: Connection
    ) -> None:
        """A quota set via the SDK is not readable through ``metadata``.

        ``set_account_metadata`` sends ``X-Account-Meta-Quota-Bytes``, which Swift
        treats as the obsoleted spelling and moves into system metadata. The
        response then carries ``X-Account-Quota-Bytes``, which the SDK's Account
        resource does not map into ``metadata`` (that only collects
        ``X-Account-Meta-*``). A client that writes a quota this way and reads it
        back the same way will always see nothing.
        """
        from emulator.core.database import db

        openstack_connection.object_store.set_account_metadata(**{"quota-bytes": "4096"})

        account = openstack_connection.object_store.get_account_metadata()
        assert account.metadata.get("quota-bytes") is None
        # It was stored, just not under the user-metadata namespace.
        stored = db.get_swift_account(
            f"AUTH_{openstack_connection.current_project_id}", create=False
        )
        assert stored is not None
        assert stored.sysmeta["quota-bytes"] == "4096"


class TestSDKSwiftContainers:
    """Container lifecycle through the SDK."""

    def test_create_and_list(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.create_container(name="docs")
        openstack_connection.object_store.create_container(name="media")

        names = sorted(c.name for c in openstack_connection.object_store.containers())
        assert names == ["docs", "media"]

    def test_delete(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.create_container(name="docs")
        openstack_connection.object_store.delete_container("docs")

        assert list(openstack_connection.object_store.containers()) == []


class TestSDKSwiftObjects:
    """Object lifecycle through the SDK."""

    def test_upload_list_and_download(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.create_container(name="docs")
        openstack_connection.object_store.upload_object(
            container="docs", name="a.txt", data=b"hello world"
        )

        names = [o.name for o in openstack_connection.object_store.objects("docs")]
        assert names == ["a.txt"]

        content = openstack_connection.object_store.download_object("a.txt", container="docs")
        assert content == b"hello world"

    def test_delete_object(self, openstack_connection: Connection) -> None:
        openstack_connection.object_store.create_container(name="docs")
        openstack_connection.object_store.upload_object(container="docs", name="a.txt", data=b"x")
        openstack_connection.object_store.delete_object("a.txt", container="docs")

        assert list(openstack_connection.object_store.objects("docs")) == []
