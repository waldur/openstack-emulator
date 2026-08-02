"""Tests for the Swift Object Storage API and account quota enforcement."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from tests.conftest import grant_scope

ACCOUNT = "AUTH_proj-1"


@pytest.fixture
def apps():
    """Build the service apps once per test."""
    return create_all_service_apps()


@pytest.fixture
def client(apps):
    """Create a Swift test client."""
    return TestClient(apps["swift"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset swift and keystone state between tests."""
    db.reset_swift()
    db.reset_keystone()
    yield


def _token(apps, user_name, project_name=None, project_id=None):
    keystone = TestClient(apps["keystone"])
    scope = {"project": {"id": project_id}} if project_id else {"project": {"name": project_name}}
    response = keystone.post(
        "/v3/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": user_name,
                            "domain": {"id": "default"},
                            "password": "s4l4dus",
                        }
                    },
                },
                "scope": scope,
            }
        },
    )
    return {"X-Auth-Token": response.headers["X-Subject-Token"]}


@pytest.fixture
def reseller(apps):
    """Headers for a privileged (reseller) token."""
    return _token(apps, "admin", project_name="admin")


@pytest.fixture
def user(apps):
    """Headers for an unprivileged token owning AUTH_proj-1."""
    grant_scope(project_name="proj-one", project_id="proj-1", user_name="member")
    return _token(apps, "member", project_id="proj-1")


class TestAccount:
    """Account-level metadata, usage totals and listings."""

    def test_head_account_reports_usage(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"hello")

        response = client.head(f"/v1/{ACCOUNT}", headers=reseller)
        assert response.status_code == 204
        assert response.headers["X-Account-Container-Count"] == "1"
        assert response.headers["X-Account-Object-Count"] == "1"
        assert response.headers["X-Account-Bytes-Used"] == "5"

    def test_json_container_listing(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"hello")
        client.put(f"/v1/{ACCOUNT}/media", headers=reseller)

        response = client.get(f"/v1/{ACCOUNT}?format=json", headers=reseller)
        assert response.status_code == 200
        listing = response.json()
        assert [c["name"] for c in listing] == ["docs", "media"]
        assert listing[0]["count"] == 1
        assert listing[0]["bytes"] == 5

    def test_empty_text_listing_is_204(self, client, reseller):
        response = client.get(f"/v1/{ACCOUNT}", headers=reseller)
        assert response.status_code == 204

    def test_account_metadata_round_trips(self, client, reseller):
        response = client.post(
            f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Meta-Owner": "waldur"}
        )
        assert response.status_code == 204

        response = client.head(f"/v1/{ACCOUNT}", headers=reseller)
        assert response.headers["X-Account-Meta-Owner"] == "waldur"

    def test_unauthenticated_is_401(self, client):
        assert client.head(f"/v1/{ACCOUNT}").status_code == 401


class TestAccountQuotaWrites:
    """Only resellers may set a quota; everyone may read it."""

    def test_reseller_sets_quota(self, client, reseller):
        response = client.post(
            f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "1000"}
        )
        assert response.status_code == 204
        assert (
            client.head(f"/v1/{ACCOUNT}", headers=reseller).headers["X-Account-Quota-Bytes"]
            == "1000"
        )

    def test_legacy_meta_header_is_accepted(self, client, reseller):
        """X-Account-Meta-Quota-Bytes is obsoleted but still translated."""
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Meta-Quota-Bytes": "512"})

        response = client.head(f"/v1/{ACCOUNT}", headers=reseller)
        assert response.headers["X-Account-Quota-Bytes"] == "512"

    def test_non_reseller_cannot_set_quota(self, client, user):
        response = client.post(f"/v1/{ACCOUNT}", headers={**user, "X-Account-Quota-Bytes": "1000"})
        assert response.status_code == 403

    def test_non_reseller_can_read_quota(self, client, reseller, user):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "1000"})

        response = client.head(f"/v1/{ACCOUNT}", headers=user)
        assert response.status_code == 204
        assert response.headers["X-Account-Quota-Bytes"] == "1000"

    def test_non_numeric_quota_is_400(self, client, reseller):
        response = client.post(
            f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "lots"}
        )
        assert response.status_code == 400

    def test_remove_header_clears_quota(self, client, reseller):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "1000"})
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Remove-Account-Quota-Bytes": "yes"})

        response = client.head(f"/v1/{ACCOUNT}", headers=reseller)
        assert "X-Account-Quota-Bytes" not in response.headers


class TestAccountQuotaEnforcement:
    """An object PUT that would exceed the account quota is refused with 413."""

    @pytest.fixture(autouse=True)
    def container(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)

    def test_upload_within_quota_succeeds(self, client, reseller, user):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "10"})

        response = client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=user, content=b"12345")
        assert response.status_code == 201

    def test_upload_exceeding_quota_is_413(self, client, reseller, user):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "10"})

        response = client.put(f"/v1/{ACCOUNT}/docs/big.txt", headers=user, content=b"x" * 11)
        assert response.status_code == 413

    def test_quota_counts_existing_usage(self, client, reseller, user):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "10"})
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=user, content=b"12345")

        response = client.put(f"/v1/{ACCOUNT}/docs/b.txt", headers=user, content=b"123456")
        assert response.status_code == 413

    def test_object_count_quota(self, client, reseller, user):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Count": "1"})
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=user, content=b"a")

        response = client.put(f"/v1/{ACCOUNT}/docs/b.txt", headers=user, content=b"b")
        assert response.status_code == 413

    def test_reseller_is_not_constrained(self, client, reseller):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "1"})

        response = client.put(f"/v1/{ACCOUNT}/docs/big.txt", headers=reseller, content=b"x" * 100)
        assert response.status_code == 201

    def test_no_quota_means_no_limit(self, client, user):
        response = client.put(f"/v1/{ACCOUNT}/docs/big.txt", headers=user, content=b"x" * 10_000)
        assert response.status_code == 201


class TestContainers:
    """Container create, list, metadata and delete."""

    def test_create_then_recreate(self, client, reseller):
        assert client.put(f"/v1/{ACCOUNT}/docs", headers=reseller).status_code == 201
        assert client.put(f"/v1/{ACCOUNT}/docs", headers=reseller).status_code == 202

    def test_head_reports_usage(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"abc")

        response = client.head(f"/v1/{ACCOUNT}/docs", headers=reseller)
        assert response.headers["X-Container-Object-Count"] == "1"
        assert response.headers["X-Container-Bytes-Used"] == "3"

    def test_object_listing(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/b.txt", headers=reseller, content=b"bb")
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"a")

        listing = client.get(f"/v1/{ACCOUNT}/docs?format=json", headers=reseller).json()
        assert [o["name"] for o in listing] == ["a.txt", "b.txt"]
        assert listing[0]["bytes"] == 1

    def test_prefix_filter(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/logs/a.txt", headers=reseller, content=b"a")
        client.put(f"/v1/{ACCOUNT}/docs/other.txt", headers=reseller, content=b"a")

        listing = client.get(
            f"/v1/{ACCOUNT}/docs?format=json&prefix=logs/", headers=reseller
        ).json()
        assert [o["name"] for o in listing] == ["logs/a.txt"]

    def test_delete_non_empty_is_409(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"a")

        assert client.delete(f"/v1/{ACCOUNT}/docs", headers=reseller).status_code == 409

    def test_delete_empty_container(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)
        assert client.delete(f"/v1/{ACCOUNT}/docs", headers=reseller).status_code == 204
        assert client.head(f"/v1/{ACCOUNT}/docs", headers=reseller).status_code == 404

    def test_unknown_container_is_404(self, client, reseller):
        assert client.head(f"/v1/{ACCOUNT}/nope", headers=reseller).status_code == 404


class TestObjects:
    """Object store, fetch and delete."""

    @pytest.fixture(autouse=True)
    def container(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs", headers=reseller)

    def test_round_trip(self, client, reseller):
        put = client.put(
            f"/v1/{ACCOUNT}/docs/a.txt",
            headers={**reseller, "Content-Type": "text/plain"},
            content=b"hello",
        )
        assert put.status_code == 201
        assert put.headers["Etag"]

        get = client.get(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller)
        assert get.status_code == 200
        assert get.content == b"hello"
        assert get.headers["Content-Type"] == "text/plain"

    def test_nested_object_names(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs/a/b/c.txt", headers=reseller, content=b"deep")
        assert client.get(f"/v1/{ACCOUNT}/docs/a/b/c.txt", headers=reseller).content == b"deep"

    def test_object_metadata(self, client, reseller):
        client.put(
            f"/v1/{ACCOUNT}/docs/a.txt",
            headers={**reseller, "X-Object-Meta-Origin": "waldur"},
            content=b"x",
        )
        response = client.head(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller)
        assert response.headers["X-Object-Meta-Origin"] == "waldur"

    def test_delete(self, client, reseller):
        client.put(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller, content=b"x")
        assert client.delete(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller).status_code == 204
        assert client.get(f"/v1/{ACCOUNT}/docs/a.txt", headers=reseller).status_code == 404

    def test_put_into_missing_container_is_404(self, client, reseller):
        response = client.put(f"/v1/{ACCOUNT}/nope/a.txt", headers=reseller, content=b"x")
        assert response.status_code == 404


class TestAccountIsolation:
    """A non-reseller is confined to the account its catalog entry names."""

    def test_other_account_is_forbidden(self, client, user):
        assert client.head("/v1/AUTH_someone-else", headers=user).status_code == 403

    def test_own_account_is_allowed(self, client, user):
        assert client.head(f"/v1/{ACCOUNT}", headers=user).status_code == 204


class TestReadsDoNotMutate:
    """Looking at an account must not bring it into existence."""

    def test_head_does_not_create_the_account(self, client, reseller):
        before = len(db.list_swift_accounts())

        response = client.head("/v1/AUTH_never-written-to", headers=reseller)

        assert response.status_code == 204
        assert response.headers["X-Account-Bytes-Used"] == "0"
        assert len(db.list_swift_accounts()) == before

    def test_get_does_not_create_the_account(self, client, reseller):
        before = len(db.list_swift_accounts())

        client.get("/v1/AUTH_also-never-written-to?format=json", headers=reseller)

        assert len(db.list_swift_accounts()) == before

    def test_a_write_does_create_the_account(self, client, reseller):
        client.post(f"/v1/{ACCOUNT}", headers={**reseller, "X-Account-Quota-Bytes": "42"})

        assert db.get_swift_account(ACCOUNT, create=False) is not None
