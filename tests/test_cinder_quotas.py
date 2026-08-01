"""Tests for Cinder per-volume-type quotas, usage reporting and quota classes."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

PROJECT = "proj-1"


@pytest.fixture
def client():
    """Create a test client."""
    apps = create_all_service_apps()
    return TestClient(apps["cinder"])


@pytest.fixture(autouse=True)
def reset_db():
    """Reset cinder state between tests."""
    db.reset_cinder()
    yield


@pytest.fixture
def headers(client):
    """Auth headers built from a real keystone token."""
    apps = create_all_service_apps()
    keystone = TestClient(apps["keystone"])
    response = keystone.post(
        "/v3/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "admin",
                            "domain": {"id": "default"},
                            "password": "s4l4dus",
                        }
                    },
                },
                "scope": {"project": {"name": "admin", "domain": {"id": "default"}}},
            }
        },
    )
    return {"X-Auth-Token": response.headers["X-Subject-Token"]}


def _quota_url(tenant=PROJECT):
    return f"/v3/{PROJECT}/os-quota-sets/{tenant}"


class TestPerVolumeTypeQuotaWrites:
    """`<metric>_<volume type>` keys round-trip instead of being dropped."""

    def test_sets_and_reads_back_per_type_limits(self, client, headers):
        response = client.put(
            _quota_url(),
            headers=headers,
            json={"quota_set": {"gigabytes_ssd": 500, "volumes_ssd": 20, "snapshots_ssd": 5}},
        )
        assert response.status_code == 200
        quota_set = response.json()["quota_set"]
        assert quota_set["gigabytes_ssd"] == 500
        assert quota_set["volumes_ssd"] == 20
        assert quota_set["snapshots_ssd"] == 5

        fetched = client.get(_quota_url(), headers=headers).json()["quota_set"]
        assert fetched["gigabytes_ssd"] == 500

    def test_totals_and_per_type_coexist(self, client, headers):
        client.put(
            _quota_url(),
            headers=headers,
            json={"quota_set": {"gigabytes": 2000, "gigabytes_ssd": 500}},
        )
        quota_set = client.get(_quota_url(), headers=headers).json()["quota_set"]
        assert quota_set["gigabytes"] == 2000
        assert quota_set["gigabytes_ssd"] == 500

    def test_partial_update_leaves_other_per_type_keys_alone(self, client, headers):
        client.put(
            _quota_url(),
            headers=headers,
            json={"quota_set": {"gigabytes_ssd": 500, "gigabytes_rbd": 100}},
        )
        client.put(_quota_url(), headers=headers, json={"quota_set": {"gigabytes_ssd": 800}})

        quota_set = client.get(_quota_url(), headers=headers).json()["quota_set"]
        assert quota_set["gigabytes_ssd"] == 800
        assert quota_set["gigabytes_rbd"] == 100

    def test_volume_type_name_containing_underscore(self, client, headers):
        db.create_volume_type(name="fast_nvme")

        response = client.put(
            _quota_url(), headers=headers, json={"quota_set": {"gigabytes_fast_nvme": 42}}
        )
        assert response.status_code == 200
        assert response.json()["quota_set"]["gigabytes_fast_nvme"] == 42


class TestPerVolumeTypeQuotaValidation:
    """A quota key naming an unknown volume type is an error, not a silent drop."""

    def test_unknown_volume_type_is_rejected(self, client, headers):
        response = client.put(
            _quota_url(), headers=headers, json={"quota_set": {"gigabytes_nosuchtype": 10}}
        )
        assert response.status_code == 400
        assert "gigabytes_nosuchtype" in response.json()["error"]["message"]

    def test_unknown_metric_is_rejected(self, client, headers):
        response = client.put(_quota_url(), headers=headers, json={"quota_set": {"bandwidth": 10}})
        assert response.status_code == 400

    def test_echoed_non_limit_keys_are_ignored(self, client, headers):
        # cinder.quota.NON_QUOTA_KEYS is exactly ["tenant_id", "id"].
        response = client.put(
            _quota_url(),
            headers=headers,
            json={"quota_set": {"id": PROJECT, "tenant_id": PROJECT, "gigabytes": 50}},
        )
        assert response.status_code == 200
        assert response.json()["quota_set"]["gigabytes"] == 50

    def test_force_is_not_a_quota_key(self, client, headers):
        response = client.put(
            _quota_url(), headers=headers, json={"quota_set": {"force": True, "gigabytes": 50}}
        )
        assert response.status_code == 400

    def test_all_bad_keys_are_reported_together(self, client, headers):
        response = client.put(
            _quota_url(),
            headers=headers,
            json={"quota_set": {"bandwidth": 1, "gigabytes_nosuchtype": 2}},
        )
        assert response.status_code == 400
        message = response.json()["error"]["message"]
        assert "bandwidth" in message
        assert "gigabytes_nosuchtype" in message


class TestQuotaUsage:
    """`usage=true` reports in_use for totals and per-volume-type keys alike."""

    def test_reports_per_type_usage(self, client, headers):
        db.create_volume(name="v1", size=30, project_id=PROJECT, user_id="u1", volume_type="ssd")
        db.create_volume(name="v2", size=10, project_id=PROJECT, user_id="u1", volume_type="rbd")
        client.put(_quota_url(), headers=headers, json={"quota_set": {"gigabytes_ssd": 500}})

        quota_set = client.get(f"{_quota_url()}?usage=true", headers=headers).json()["quota_set"]

        assert quota_set["gigabytes"]["in_use"] == 40
        assert quota_set["volumes"]["in_use"] == 2
        assert quota_set["gigabytes_ssd"] == {"limit": 500, "in_use": 30, "reserved": 0}

    def test_usage_shape_covers_every_limit_key(self, client, headers):
        client.put(_quota_url(), headers=headers, json={"quota_set": {"volumes_ssd": 3}})

        quota_set = client.get(f"{_quota_url()}?usage=true", headers=headers).json()["quota_set"]

        for key, value in quota_set.items():
            if key == "id":
                continue
            assert set(value) == {"limit", "in_use", "reserved"}

    def test_usage_is_scoped_to_the_project(self, client, headers):
        db.create_volume(name="mine", size=5, project_id=PROJECT, user_id="u1", volume_type="ssd")
        db.create_volume(
            name="theirs", size=99, project_id="other", user_id="u2", volume_type="ssd"
        )

        quota_set = client.get(f"{_quota_url()}?usage=true", headers=headers).json()["quota_set"]
        assert quota_set["gigabytes"]["in_use"] == 5


class TestQuotaClassSets:
    """Quota classes hold the limits new projects inherit."""

    def test_defaults_are_returned_for_an_unseen_class(self, client, headers):
        response = client.get(f"/v3/{PROJECT}/os-quota-class-sets/default", headers=headers)
        assert response.status_code == 200
        body = response.json()["quota_class_set"]
        assert body["id"] == "default"
        assert body["volumes"] == 10

    def test_update_round_trips(self, client, headers):
        response = client.put(
            f"/v3/{PROJECT}/os-quota-class-sets/default",
            headers=headers,
            json={"quota_class_set": {"volumes": 42, "gigabytes_ssd": 900}},
        )
        assert response.status_code == 200

        body = client.get(f"/v3/{PROJECT}/os-quota-class-sets/default", headers=headers).json()[
            "quota_class_set"
        ]
        assert body["volumes"] == 42
        assert body["gigabytes_ssd"] == 900
