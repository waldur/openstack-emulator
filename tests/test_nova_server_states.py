"""Server actions follow Nova's vm_state / task_state rules.

The allowed states come from the ``check_instance_state`` decorators in
nova/compute/api.py, the shown status from ``_STATE_MAP`` in
nova/api/openstack/common.py, and the 409 wording from Nova's
``InstanceInvalidState``, which clients match on.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core import database
from emulator.core.database import Database, db
from emulator.core.models import ServerStatus, TaskState
from tests.conftest import scoped_token


@pytest.fixture
def client():
    return TestClient(create_all_service_apps()["nova"])


@pytest.fixture
def headers():
    token = db.create_token(user_name="admin", project_name="admin", domain_id="default")
    return {"X-Auth-Token": token.id}


@pytest.fixture(autouse=True)
def no_servers():
    db._servers.clear()
    yield


def create_server(client, headers):
    image_id = client.get("/v2.1/images", headers=headers).json()["images"][0]["id"]
    response = client.post(
        "/v2.1/servers",
        headers=headers,
        json={"server": {"name": "vm", "flavorRef": "1", "imageRef": image_id}},
    )
    assert response.status_code == 202
    return response.json()["server"]["id"]


@pytest.fixture
def server_id(client, headers):
    return create_server(client, headers)


@pytest.fixture
def clock(monkeypatch):
    """A clock the test moves by hand, with server actions taking 30 seconds."""

    class Clock:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def tick(self, seconds):
            self.now += timedelta(seconds=seconds)

    clock = Clock()
    monkeypatch.setattr(database, "_utcnow", lambda: clock.now)
    monkeypatch.setattr(db, "server_action_seconds", 30.0)
    return clock


def act(client, headers, server_id, body):
    return client.post(f"/v2.1/servers/{server_id}/action", headers=headers, json=body)


def show(client, headers, server_id):
    server = client.get(f"/v2.1/servers/{server_id}", headers=headers).json()["server"]
    return server["status"], server["OS-EXT-STS:task_state"], server["OS-EXT-STS:vm_state"]


def conflict(response):
    assert response.status_code == 409, response.text
    return response.json()["error"]["message"]


class TestServerStateRules:
    def test_soft_reboot_of_a_stopped_server_is_refused_in_novas_words(
        self, client, headers, server_id
    ):
        act(client, headers, server_id, {"os-stop": None})

        response = act(client, headers, server_id, {"reboot": {"type": "SOFT"}})

        assert conflict(response) == (
            f"Cannot 'reboot' instance {server_id} while it is in vm_state stopped"
        )

    def test_hard_reboot_starts_a_stopped_server(self, client, headers, server_id):
        act(client, headers, server_id, {"os-stop": None})

        response = act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        assert response.status_code == 202
        assert show(client, headers, server_id) == ("ACTIVE", None, "active")

    @pytest.mark.parametrize(
        "into",
        [{"os-resetState": {"state": "error"}}, {"pause": None}, {"suspend": None}],
        ids=["error", "paused", "suspended"],
    )
    def test_hard_reboot_recovers_a_server(self, client, headers, server_id, into):
        assert act(client, headers, server_id, into).status_code == 202

        response = act(client, headers, server_id, {"reboot": {"type": "hard"}})

        assert response.status_code == 202
        assert show(client, headers, server_id) == ("ACTIVE", None, "active")

    @pytest.mark.parametrize("into", [{"pause": None}, {"suspend": None}])
    def test_soft_reboot_is_refused_outside_active(self, client, headers, server_id, into):
        act(client, headers, server_id, into)

        response = act(client, headers, server_id, {"reboot": {"type": "SOFT"}})

        assert "while it is in vm_state" in conflict(response)

    def test_reboot_type_must_be_soft_or_hard(self, client, headers, server_id):
        response = act(client, headers, server_id, {"reboot": {"type": "WARM"}})

        assert response.status_code == 400

    def test_starting_an_active_server_names_its_vm_state(self, client, headers, server_id):
        response = act(client, headers, server_id, {"os-start": None})

        assert conflict(response).endswith("while it is in vm_state active")

    def test_stopping_a_stopped_server_names_its_vm_state(self, client, headers, server_id):
        act(client, headers, server_id, {"os-stop": None})

        response = act(client, headers, server_id, {"os-stop": None})

        assert conflict(response).endswith("while it is in vm_state stopped")

    def test_a_stopped_server_reports_novas_vm_state(self, client, headers, server_id):
        act(client, headers, server_id, {"os-stop": None})

        assert show(client, headers, server_id) == ("SHUTOFF", None, "stopped")

    def test_an_errored_server_can_be_stopped(self, client, headers, server_id):
        act(client, headers, server_id, {"os-resetState": {"state": "error"}})

        response = act(client, headers, server_id, {"os-stop": None})

        assert response.status_code == 202
        assert show(client, headers, server_id) == ("SHUTOFF", None, "stopped")

    def test_reset_state_is_admin_only(self, client):
        member = {"X-Auth-Token": scoped_token(project_name="tenant-one").id}
        own_server = create_server(client, member)

        response = act(client, member, own_server, {"os-resetState": {"state": "error"}})

        assert response.status_code == 403
        assert db.get_server(own_server).status == ServerStatus.ACTIVE

    def test_reset_state_takes_active_or_error(self, client, headers, server_id):
        response = act(client, headers, server_id, {"os-resetState": {"state": "stopped"}})

        assert response.status_code == 400

    def test_fault_is_shown_only_while_in_error(self, client, headers, server_id):
        act(client, headers, server_id, {"os-resetState": {"state": "error"}})
        db.get_server(server_id).fault = {"code": 500, "message": "boom"}
        server = client.get(f"/v2.1/servers/{server_id}", headers=headers).json()["server"]
        assert server["fault"]["message"] == "boom"

        act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        server = client.get(f"/v2.1/servers/{server_id}", headers=headers).json()["server"]
        assert "fault" not in server


class TestTimedServerActions:
    def test_hard_reboot_of_an_errored_server_keeps_reporting_error(
        self, client, headers, server_id, clock
    ):
        act(client, headers, server_id, {"os-resetState": {"state": "error"}})

        act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        assert show(client, headers, server_id) == ("ERROR", "rebooting_hard", "error")
        clock.tick(12)
        assert show(client, headers, server_id) == ("ERROR", "reboot_pending_hard", "error")
        clock.tick(10)
        assert show(client, headers, server_id) == ("ERROR", "reboot_started_hard", "error")
        clock.tick(10)
        assert show(client, headers, server_id) == ("ACTIVE", None, "active")

    @pytest.mark.parametrize(
        ("reboot_type", "status", "task_state"),
        [("SOFT", "REBOOT", "rebooting"), ("HARD", "HARD_REBOOT", "rebooting_hard")],
    )
    def test_an_active_server_shows_its_reboot(
        self, client, headers, server_id, clock, reboot_type, status, task_state
    ):
        act(client, headers, server_id, {"reboot": {"type": reboot_type}})

        assert show(client, headers, server_id) == (status, task_state, "active")
        clock.tick(30)
        assert show(client, headers, server_id) == ("ACTIVE", None, "active")

    def test_stop_powers_off_before_the_status_changes(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"os-stop": None})

        assert show(client, headers, server_id) == ("ACTIVE", "powering-off", "active")
        clock.tick(30)
        assert show(client, headers, server_id) == ("SHUTOFF", None, "stopped")

    def test_other_actions_wait_for_the_task(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"reboot": {"type": "SOFT"}})

        response = act(client, headers, server_id, {"os-stop": None})

        assert conflict(response) == (
            f"Cannot 'stop' instance {server_id} while it is in task_state rebooting"
        )

    def test_hard_reboot_takes_over_a_soft_reboot(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"reboot": {"type": "SOFT"}})

        response = act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        assert response.status_code == 202
        assert show(client, headers, server_id) == ("HARD_REBOOT", "rebooting_hard", "active")

    def test_a_running_hard_reboot_cannot_be_restarted(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"reboot": {"type": "HARD"}})
        clock.tick(25)

        response = act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        assert conflict(response).endswith("while it is in task_state reboot_started_hard")

    def test_listing_filters_on_the_shown_status(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        listed = client.get("/v2.1/servers?status=HARD_REBOOT", headers=headers).json()

        assert [s["id"] for s in listed["servers"]] == [server_id]

    def test_reset_state_drops_the_task(self, client, headers, server_id, clock):
        act(client, headers, server_id, {"reboot": {"type": "HARD"}})

        act(client, headers, server_id, {"os-resetState": {"state": "error"}})

        assert show(client, headers, server_id) == ("ERROR", None, "error")
        clock.tick(60)
        assert show(client, headers, server_id) == ("ERROR", None, "error")


def test_a_task_in_progress_survives_a_restart(monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(database, "_utcnow", lambda: now)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "db.json")
        first = Database(persist_path=path)
        first.server_action_seconds = 30.0
        server = first.create_server(name="vm", flavor_id="1", image_id="cirros", tenant_id="p1")
        first.server_action(server.id, "reboot", reboot_type="HARD")
        first.save()

        second = Database(persist_path=path)
        second.load()

        loaded = second.get_server(server.id)
        assert loaded.task_state == TaskState.REBOOTING_HARD
        monkeypatch.setattr(database, "_utcnow", lambda: now + timedelta(seconds=31))
        assert second.get_server(server.id).status == ServerStatus.ACTIVE
