"""Tests for Scenario management and failure injection."""

import time

import pytest
from fastapi.testclient import TestClient

from emulator.api.app_scenarios import app as scenarios_app
from emulator.api.app_nova import app as nova_app
from emulator.core.database import db
from emulator.core.scenario_manager import scenario_manager
from emulator.core.scenarios import (
    DelayDistribution,
    FailureConfig,
    FailureType,
    LoadProfile,
    Scenario,
    ScenarioCategory,
)


@pytest.fixture(autouse=True)
def reset_state():
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
def scenarios_client():
    """Create test client for scenarios API."""
    return TestClient(scenarios_app)


@pytest.fixture
def nova_client():
    """Create test client for Nova API."""
    return TestClient(nova_app)


@pytest.fixture
def auth_token(nova_client):
    """Get an authentication token."""
    # Use a separate client for keystone
    from emulator.api.app_keystone import app as keystone_app

    keystone_client = TestClient(keystone_app)
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
    return response.headers["X-Subject-Token"]


class TestScenarioManager:
    """Test the scenario manager functionality."""

    def test_list_builtin_scenarios(self):
        """Test that builtin scenarios are registered."""
        scenarios = scenario_manager.list_scenarios()
        assert len(scenarios) > 0

        # Check for some expected builtin scenarios
        scenario_ids = [s.id for s in scenarios]
        assert "system_under_load" in scenario_ids
        assert "nova_oom_crash" in scenario_ids
        assert "cinder_disk_full" in scenario_ids

    def test_enable_disable_scenario(self):
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

    def test_reset_scenarios(self):
        """Test resetting all scenarios."""
        # Enable multiple scenarios
        scenario_manager.enable_scenario("light_load")
        scenario_manager.enable_scenario("nova_slow")
        assert len(scenario_manager.get_active_scenarios()) == 2

        # Reset
        scenario_manager.reset()
        assert len(scenario_manager.get_active_scenarios()) == 0

    def test_register_custom_scenario(self):
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

    def test_filter_scenarios_by_category(self):
        """Test filtering scenarios by category."""
        performance = scenario_manager.list_scenarios(
            category=ScenarioCategory.PERFORMANCE
        )
        assert all(s.category == ScenarioCategory.PERFORMANCE for s in performance)
        assert len(performance) > 0

        storage = scenario_manager.list_scenarios(category=ScenarioCategory.STORAGE)
        assert all(s.category == ScenarioCategory.STORAGE for s in storage)

    def test_filter_scenarios_by_service(self):
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

    def test_uniform_distribution(self):
        """Test uniform delay distribution."""
        scenario_manager.enable_scenario("light_load")

        delays = []
        for _ in range(100):
            result = scenario_manager.calculate_delay("nova", "read")
            delays.append(result.delay_ms)

        # Should have some variation
        assert min(delays) >= 100
        assert max(delays) <= 500

    def test_stacking_delays(self):
        """Test that delays from multiple scenarios stack."""
        # Enable two scenarios
        scenario_manager.enable_scenario("light_load")
        scenario_manager.enable_scenario("nova_slow")

        # Get delay for nova (should be combined)
        result = scenario_manager.calculate_delay("nova", "read")

        # Combined delay should be higher than individual minimums
        # light_load: 100-500ms, nova_slow: 1000-5000ms
        assert result.delay_ms >= 1100  # At least the minimums combined

    def test_service_specific_delay(self):
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

    def test_service_unavailable(self):
        """Test service unavailable failure."""
        scenario_manager.enable_scenario("nova_oom_crash")

        failure = scenario_manager.should_fail("nova", "read")
        assert failure is not None
        assert failure.should_fail is True
        assert failure.status_code == 503
        assert failure.scenario_id == "nova_oom_crash"

    def test_intermittent_failure(self):
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

    def test_operation_filtering(self):
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

    def test_list_scenarios(self, scenarios_client):
        """Test listing scenarios."""
        response = scenarios_client.get("/scenarios")
        assert response.status_code == 200

        data = response.json()
        assert "scenarios" in data
        assert len(data["scenarios"]) > 0
        assert "categories" in data
        assert "failure_types" in data

    def test_get_scenario(self, scenarios_client):
        """Test getting a specific scenario."""
        response = scenarios_client.get("/scenarios/light_load")
        assert response.status_code == 200

        data = response.json()
        assert data["scenario"]["id"] == "light_load"
        assert data["scenario"]["name"] == "Light Load"

    def test_get_nonexistent_scenario(self, scenarios_client):
        """Test getting a scenario that doesn't exist."""
        response = scenarios_client.get("/scenarios/nonexistent")
        assert response.status_code == 404

    def test_enable_scenario_api(self, scenarios_client):
        """Test enabling a scenario via API."""
        response = scenarios_client.post("/scenarios/light_load/enable")
        assert response.status_code == 200

        data = response.json()
        assert "enabled" in data["message"].lower()

        # Verify it's enabled
        active = scenarios_client.get("/scenarios/active")
        assert any(s["id"] == "light_load" for s in active.json()["active_scenarios"])

    def test_disable_scenario_api(self, scenarios_client):
        """Test disabling a scenario via API."""
        # First enable
        scenarios_client.post("/scenarios/light_load/enable")

        # Then disable
        response = scenarios_client.post("/scenarios/light_load/disable")
        assert response.status_code == 200

        # Verify it's disabled
        active = scenarios_client.get("/scenarios/active")
        assert not any(
            s["id"] == "light_load" for s in active.json()["active_scenarios"]
        )

    def test_reset_scenarios_api(self, scenarios_client):
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

    def test_apply_preset(self, scenarios_client):
        """Test applying a preset."""
        response = scenarios_client.post("/scenarios/preset/heavy")
        assert response.status_code == 200

        # Verify preset is active
        active = scenarios_client.get("/scenarios/active")
        active_ids = [s["id"] for s in active.json()["active_scenarios"]]
        assert "heavy_load" in active_ids

    def test_set_load_level(self, scenarios_client):
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

    def test_get_stats(self, scenarios_client):
        """Test getting injection statistics."""
        response = scenarios_client.get("/scenarios/stats")
        assert response.status_code == 200

        data = response.json()
        assert "global" in data
        assert "scenarios" in data


class TestMiddlewareIntegration:
    """Test that middleware properly intercepts requests."""

    def test_health_endpoint_bypasses_middleware(self, nova_client):
        """Test that health endpoint is not affected by scenarios."""
        scenario_manager.enable_scenario("nova_oom_crash")

        response = nova_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_delay_injection(self, nova_client, auth_token):
        """Test that delays are actually injected."""
        # Enable a scenario with known delay
        scenario_manager.enable_scenario("light_load")

        # Time a request
        start = time.time()
        response = nova_client.get(
            "/v2.1/flavors",
            headers={"X-Auth-Token": auth_token},
        )
        elapsed = time.time() - start

        # Should have some delay (at least 100ms)
        assert elapsed >= 0.1
        assert response.status_code == 200

    def test_failure_injection(self, nova_client, auth_token):
        """Test that failures are injected."""
        scenario_manager.enable_scenario("nova_oom_crash")

        response = nova_client.get(
            "/v2.1/servers",
            headers={"X-Auth-Token": auth_token},
        )

        # Should get 503 Service Unavailable
        assert response.status_code == 503
        assert "error" in response.json()
