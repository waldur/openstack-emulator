"""Tests for the per-request access log.

The services share one process and one stdout, so the access line is the only
thing that says which service answered a request. It had no test coverage, and
a middleware-ordering mistake meant injected failures produced no line at all.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.scenario_manager import scenario_manager

_apps = create_all_service_apps()


@pytest.fixture(autouse=True)
def reset_scenarios():
    scenario_manager.reset()
    yield
    scenario_manager.reset()


@pytest.fixture
def access_lines(caplog):
    caplog.set_level(logging.INFO, logger="emulator.access")

    def lines():
        return [r.getMessage() for r in caplog.records if r.name == "emulator.access"]

    return lines


class TestAccessLog:
    def test_logs_one_line_naming_the_service(self, access_lines):
        TestClient(_apps["nova"]).get("/v2.1/flavors", headers={"X-Auth-Token": "nope"})

        lines = access_lines()
        assert len(lines) == 1
        assert lines[0].startswith("nova:")
        assert '"GET /v2.1/flavors HTTP/1.1" 401' in lines[0]

    def test_each_service_names_itself(self, access_lines):
        TestClient(_apps["neutron"]).get("/v2.0/networks")
        TestClient(_apps["keystone"]).get("/v3")

        prefixes = [line.split(":")[0] for line in access_lines()]
        assert prefixes == ["neutron", "keystone"]

    def test_query_string_is_included(self, access_lines):
        TestClient(_apps["neutron"]).get("/v2.0/networks?tenant_id=abc")

        assert "/v2.0/networks?tenant_id=abc" in access_lines()[0]

    def test_injected_failures_are_logged(self, access_lines):
        """The regression: ScenarioMiddleware short-circuits the response.

        With the access log registered inside it, an injected 503 produced no
        line at all — the one response you most want to see in a log was the
        one response that left no trace.
        """
        scenario_manager.enable_scenario("nova_oom_crash")

        response = TestClient(_apps["nova"]).get("/v2.1/flavors", headers={"X-Auth-Token": "nope"})

        assert response.status_code == 503
        lines = access_lines()
        assert len(lines) == 1
        assert '"GET /v2.1/flavors HTTP/1.1" 503' in lines[0]

    def test_unmatched_routes_are_logged(self, access_lines):
        response = TestClient(_apps["nova"]).get("/v2.1/no-such-endpoint")

        assert response.status_code == 404
        assert '"GET /v2.1/no-such-endpoint HTTP/1.1" 404' in access_lines()[0]

    def test_health_checks_are_logged(self, access_lines):
        TestClient(_apps["nova"]).get("/health")

        assert '"GET /health HTTP/1.1" 200' in access_lines()[0]
