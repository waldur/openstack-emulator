"""Tests for Scenario management and failure injection."""

import time
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.scenario_manager import scenario_manager
from emulator.core.scenarios import (
    FailureType,
    LoadProfile,
    Scenario,
    ScenarioCategory,
)

# Create all apps once at module level
_apps = create_all_service_apps()


@pytest.fixture(autouse=True)
def reset_state() -> Generator[None, None, None]:
    """Reset scenario manager and database before each test."""
    scenario_manager.reset()
    db._servers.clear()
    db._tokens.clear()
    db._init_default_flavors()
    db._init_default_images()
    db.reset_keystone()
    yield
    scenario_manager.reset()


@pytest.fixture
def scenarios_client() -> TestClient:
    """Create test client for scenarios API."""
    return TestClient(_apps["scenarios"])


@pytest.fixture
def nova_client() -> TestClient:
    """Create test client for Nova API."""
    return TestClient(_apps["nova"])


@pytest.fixture
def auth_token(nova_client: TestClient) -> str:
    """Get an authentication token."""
    # Use a separate client for keystone
    keystone_client = TestClient(_apps["keystone"])
    response = keystone_client.post(
        "/v3/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "admin",
                            "domain": {"name": "Default"},
                            "password": "secret",
                        }
                    },
                },
                "scope": {"project": {"name": "admin", "domain": {"name": "Default"}}},
            }
        },
    )
    assert response.status_code == 200
    return str(response.headers["X-Subject-Token"])


class TestScenarioManager:
    """Test the scenario manager functionality."""

    def test_list_builtin_scenarios(self) -> None:
        """Test that builtin scenarios are registered."""
        scenarios = scenario_manager.list_scenarios()
        assert len(scenarios) > 0

        # Check for some expected builtin scenarios
        scenario_ids = [s.id for s in scenarios]
        assert "system_under_load" in scenario_ids
        assert "nova_oom_crash" in scenario_ids
        assert "cinder_disk_full" in scenario_ids

    def test_enable_disable_scenario(self) -> None:
        """Test enabling and disabling scenarios."""
        # Initially no active scenarios
        active = scenario_manager.get_active_scenarios()
        assert len(active) == 0

        # Enable a scenario
        scenario = scenario_manager.enable_scenario("light_load")
        assert scenario is not None
        assert scenario.enabled is True

        active = scenario_manager.get_active_scenarios()
        assert len(active) == 1
        assert active[0].id == "light_load"

        # Disable the scenario
        scenario = scenario_manager.disable_scenario("light_load")
        assert scenario is not None
        assert scenario.enabled is False

        active = scenario_manager.get_active_scenarios()
        assert len(active) == 0

    def test_reset_scenarios(self) -> None:
        """Test resetting all scenarios."""
        # Enable multiple scenarios
        scenario_manager.enable_scenario("light_load")
        scenario_manager.enable_scenario("nova_slow")
        assert len(scenario_manager.get_active_scenarios()) == 2

        # Reset
        scenario_manager.reset()
        assert len(scenario_manager.get_active_scenarios()) == 0

    def test_register_custom_scenario(self) -> None:
        """Test registering a custom scenario."""
        custom = Scenario(
            id="custom_test",
            name="Custom Test Scenario",
            description="A test scenario",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            load_profile=LoadProfile(min_delay_ms=100, max_delay_ms=200),
        )

        registered = scenario_manager.register_scenario(custom)
        assert registered.id == "custom_test"
        assert registered.builtin is False

        # Can retrieve it
        retrieved = scenario_manager.get_scenario("custom_test")
        assert retrieved is not None
        assert retrieved.name == "Custom Test Scenario"

        # Can unregister
        assert scenario_manager.unregister_scenario("custom_test") is True

        # Cannot unregister builtin
        assert scenario_manager.unregister_scenario("light_load") is False

    def test_filter_scenarios_by_category(self) -> None:
        """Test filtering scenarios by category."""
        performance = scenario_manager.list_scenarios(category=ScenarioCategory.PERFORMANCE)
        assert all(s.category == ScenarioCategory.PERFORMANCE for s in performance)
        assert len(performance) > 0

        storage = scenario_manager.list_scenarios(category=ScenarioCategory.STORAGE)
        assert all(s.category == ScenarioCategory.STORAGE for s in storage)

    def test_filter_scenarios_by_service(self) -> None:
        """Test getting active scenarios filtered by service."""
        # Enable a nova-specific scenario
        scenario_manager.enable_scenario("nova_slow")

        # Enable a global scenario
        scenario_manager.enable_scenario("system_under_load")

        # Nova should see both
        nova_scenarios = scenario_manager.get_active_scenarios("nova")
        assert len(nova_scenarios) == 2

        # Cinder should only see global
        cinder_scenarios = scenario_manager.get_active_scenarios("cinder")
        assert len(cinder_scenarios) == 1
        assert cinder_scenarios[0].target_service is None


class TestDelayCalculation:
    """Test delay calculation logic."""

    def test_uniform_distribution(self) -> None:
        """Test uniform delay distribution."""
        scenario_manager.enable_scenario("light_load")

        delays = []
        for _ in range(100):
            result = scenario_manager.calculate_delay("nova", "read")
            delays.append(result.delay_ms)

        # Should have some variation
        assert min(delays) >= 100
        assert max(delays) <= 500

    def test_stacking_delays(self) -> None:
        """Test that delays from multiple scenarios stack."""
        # Enable two scenarios
        scenario_manager.enable_scenario("light_load")
        scenario_manager.enable_scenario("nova_slow")

        # Get delay for nova (should be combined)
        result = scenario_manager.calculate_delay("nova", "read")

        # Combined delay should be higher than individual minimums
        # light_load: 100-500ms, nova_slow: 1000-5000ms
        assert result.delay_ms >= 1100  # At least the minimums combined

    def test_service_specific_delay(self) -> None:
        """Test that service-specific scenarios only affect that service."""
        scenario_manager.enable_scenario("nova_slow")

        # Nova should have delay
        nova_result = scenario_manager.calculate_delay("nova", "read")
        assert nova_result.delay_ms > 0

        # Cinder should have no delay (nova_slow targets nova only)
        cinder_result = scenario_manager.calculate_delay("cinder", "read")
        assert cinder_result.delay_ms == 0


class TestFailureInjection:
    """Test failure injection logic."""

    def test_service_unavailable(self) -> None:
        """Test service unavailable failure."""
        scenario_manager.enable_scenario("nova_oom_crash")

        failure = scenario_manager.should_fail("nova", "read")
        assert failure is not None
        assert failure.should_fail is True
        assert failure.status_code == 503
        assert failure.scenario_id == "nova_oom_crash"

    def test_intermittent_failure(self) -> None:
        """Test intermittent failures with probability."""
        scenario_manager.enable_scenario("rabbitmq_unstable")

        # Run multiple times - some should fail, some should pass
        failures = 0
        passes = 0
        for _ in range(100):
            result = scenario_manager.should_fail(None, "create")
            if result is not None and result.should_fail:
                failures += 1
            else:
                passes += 1

        # With 30% failure probability, expect some variation
        assert failures > 0
        assert passes > 0

    def test_operation_filtering(self) -> None:
        """Test that failures can be filtered by operation type."""
        scenario_manager.enable_scenario("cinder_disk_full")

        # Create operations should fail
        create_failure = scenario_manager.should_fail("cinder", "create")
        assert create_failure is not None
        assert create_failure.should_fail is True

        # Read operations should not fail
        read_failure = scenario_manager.should_fail("cinder", "read")
        assert read_failure is None


class TestScenarioAPI:
    """Test the scenario management API."""

    def test_list_scenarios(self, scenarios_client: TestClient) -> None:
        """Test listing scenarios."""
        response = scenarios_client.get("/scenarios")
        assert response.status_code == 200

        data = response.json()
        assert "scenarios" in data
        assert len(data["scenarios"]) > 0
        assert "categories" in data
        assert "failure_types" in data

    def test_get_scenario(self, scenarios_client: TestClient) -> None:
        """Test getting a specific scenario."""
        response = scenarios_client.get("/scenarios/light_load")
        assert response.status_code == 200

        data = response.json()
        assert data["scenario"]["id"] == "light_load"
        assert data["scenario"]["name"] == "Light Load"

    def test_get_nonexistent_scenario(self, scenarios_client: TestClient) -> None:
        """Test getting a scenario that doesn't exist."""
        response = scenarios_client.get("/scenarios/nonexistent")
        assert response.status_code == 404

    def test_enable_scenario_api(self, scenarios_client: TestClient) -> None:
        """Test enabling a scenario via API."""
        response = scenarios_client.post("/scenarios/light_load/enable")
        assert response.status_code == 200

        data = response.json()
        assert "enabled" in data["message"].lower()

        # Verify it's enabled
        active = scenarios_client.get("/scenarios/active")
        assert any(s["id"] == "light_load" for s in active.json()["active_scenarios"])

    def test_disable_scenario_api(self, scenarios_client: TestClient) -> None:
        """Test disabling a scenario via API."""
        # First enable
        scenarios_client.post("/scenarios/light_load/enable")

        # Then disable
        response = scenarios_client.post("/scenarios/light_load/disable")
        assert response.status_code == 200

        # Verify it's disabled
        active = scenarios_client.get("/scenarios/active")
        assert not any(s["id"] == "light_load" for s in active.json()["active_scenarios"])

    def test_reset_scenarios_api(self, scenarios_client: TestClient) -> None:
        """Test resetting all scenarios via API."""
        # Enable some scenarios
        scenarios_client.post("/scenarios/light_load/enable")
        scenarios_client.post("/scenarios/nova_slow/enable")

        # Reset
        response = scenarios_client.post("/scenarios/reset")
        assert response.status_code == 200

        # Verify all disabled
        active = scenarios_client.get("/scenarios/active")
        assert len(active.json()["active_scenarios"]) == 0

    def test_apply_preset(self, scenarios_client: TestClient) -> None:
        """Test applying a preset."""
        response = scenarios_client.post("/scenarios/preset/overloaded")
        assert response.status_code == 200

        # Verify preset scenarios are active (overloaded enables multiple)
        active = scenarios_client.get("/scenarios/active")
        active_ids = [s["id"] for s in active.json()["active_scenarios"]]
        assert "heavy_load" in active_ids
        assert "rabbitmq_unstable" in active_ids
        assert "database_slow" in active_ids

    def test_set_load_level(self, scenarios_client: TestClient) -> None:
        """Test setting load level."""
        response = scenarios_client.post(
            "/scenarios/load",
            json={"level": 50},
        )
        assert response.status_code == 200
        assert "50%" in response.json()["message"]

        # Verify scenario is created and active
        active = scenarios_client.get("/scenarios/active")
        active_ids = [s["id"] for s in active.json()["active_scenarios"]]
        assert "load_level_all" in active_ids

    def test_get_stats(self, scenarios_client: TestClient) -> None:
        """Test getting injection statistics."""
        response = scenarios_client.get("/scenarios/stats")
        assert response.status_code == 200

        data = response.json()
        assert "global" in data
        assert "scenarios" in data


class TestMiddlewareIntegration:
    """Test that middleware properly intercepts requests."""

    def test_health_endpoint_bypasses_middleware(self, nova_client: TestClient) -> None:
        """Test that health endpoint is not affected by scenarios."""
        scenario_manager.enable_scenario("nova_oom_crash")

        response = nova_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_delay_injection(self, nova_client: TestClient, auth_token: str) -> None:
        """Delay-only scenarios slow a request down instead of failing it."""
        scenario_manager.enable_scenario("system_under_load")

        started = time.monotonic()
        response = nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})
        elapsed_ms = (time.monotonic() - started) * 1000

        assert response.status_code == 200
        # system_under_load injects 500-3000ms; allow slack on a busy machine.
        assert elapsed_ms >= 400

    def test_failure_injection(self, nova_client: TestClient, auth_token: str) -> None:
        """Test that failures are injected."""
        scenario_manager.enable_scenario("nova_oom_crash")

        response = nova_client.get(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
        )

        # Should get 503 Service Unavailable
        assert response.status_code == 503
        assert "error" in response.json()


class TestControlPlaneReachesDataPlane:
    """Enable a scenario the way a user does, then check it actually fires.

    The suite used to drive the scenarios API and the injection middleware
    separately, asserting each half against a different manager instance. Both
    halves passed while the feature did nothing: the API wrote one singleton and
    the middleware read another, so an "enabled" scenario never affected a
    single request. These tests cross that seam.
    """

    def test_enabling_via_the_api_makes_nova_fail(
        self, scenarios_client: TestClient, nova_client: TestClient, auth_token: str
    ) -> None:
        ok = nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})
        assert ok.status_code == 200

        enable = scenarios_client.post("/scenarios/nova_oom_crash/enable", json={})
        assert enable.status_code == 200

        response = nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})

        assert response.status_code == 503
        assert response.json()["error"]["scenario"] == "nova_oom_crash"
        assert response.headers["X-Scenario-Injection"] == "nova_oom_crash"

    def test_disabling_via_the_api_stops_the_failures(
        self, scenarios_client: TestClient, nova_client: TestClient, auth_token: str
    ) -> None:
        scenarios_client.post("/scenarios/nova_oom_crash/enable", json={})
        assert (
            nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token}).status_code
            == 503
        )

        scenarios_client.post("/scenarios/nova_oom_crash/disable")

        response = nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

    def test_reset_via_the_api_stops_the_failures(
        self, scenarios_client: TestClient, nova_client: TestClient, auth_token: str
    ) -> None:
        scenarios_client.post("/scenarios/nova_oom_crash/enable", json={})

        scenarios_client.post("/scenarios/reset")

        response = nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

    def test_scenario_only_affects_its_target_service(
        self, scenarios_client: TestClient, nova_client: TestClient, auth_token: str
    ) -> None:
        scenarios_client.post("/scenarios/nova_oom_crash/enable", json={})

        neutron = TestClient(_apps["neutron"])
        response = neutron.get("/v2.0/networks", headers={"X-Auth-Token": auth_token})

        assert response.status_code == 200

    def test_stats_record_the_injections(
        self, scenarios_client: TestClient, nova_client: TestClient, auth_token: str
    ) -> None:
        """Stats reported zero forever, which made the disconnect look like success."""
        scenarios_client.post("/scenarios/nova_oom_crash/enable", json={})

        for _ in range(3):
            nova_client.get("/v2.1/flavors", headers={"X-Auth-Token": auth_token})

        stats = scenarios_client.get("/scenarios/stats").json()["global"]
        assert stats["failures_injected"] == 3
        assert stats["last_triggered"] is not None


class TestNewServiceResourceTargeting:
    """Failure injection can target the resources of the newer services.

    ``get_resource_from_path`` matches against a lowercased path, so a pattern
    carrying uppercase (``/v1/AUTH``) would silently never match and the request
    would fall back to the catch-all "all" resource.
    """

    def test_object_storage_paths_are_recognised(self):
        from emulator.core.middleware import get_resource_from_path

        assert get_resource_from_path("/v1/AUTH_proj/backups/dump.tar") == "object_store"
        assert get_resource_from_path("/v1/AUTH_proj") == "object_store"

    def test_rating_paths_are_recognised(self):
        from emulator.core.middleware import get_resource_from_path

        assert get_resource_from_path("/v2/summary") == "rating"
        assert get_resource_from_path("/v2/dataframes") == "rating"

    def test_existing_mappings_still_win(self):
        from emulator.core.middleware import get_resource_from_path

        assert get_resource_from_path("/v2.1/servers") == "server"
        assert get_resource_from_path("/v3/projects") == "project"
