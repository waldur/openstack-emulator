"""Simplified scenario management for single-process emulator."""

import random
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from emulator.core.scenarios import (
    Scenario,
    ScenarioStats,
    get_builtin_scenarios,
)


@dataclass
class FailureResult:
    """Result of a failure check - indicates if/how a request should fail."""

    should_fail: bool = False
    status_code: int = 500
    error_message: str = "Internal server error"
    delay_seconds: float = 0.0
    scenario_id: str | None = None
    failure_type: str | None = None

    @property
    def message(self) -> str:
        """Alias for error_message for backwards compatibility."""
        return self.error_message


class SimpleScenarioManager:
    """
    Simplified scenario manager for single-process emulator.

    Uses direct in-memory state sharing instead of file-based synchronization.
    """

    def __init__(self):
        """Initialize the scenario manager."""
        self._lock = threading.RLock()
        self._enabled_scenarios: Dict[str, Scenario] = {}
        self._global_stats = ScenarioStats()

        # Load built-in scenarios
        self._available_scenarios = {s.id: s for s in get_builtin_scenarios()}

    def enable_scenario(self, scenario_id: str, config_override: Dict[str, Any] = None) -> bool:
        """
        Enable a scenario by ID.

        Args:
            scenario_id: The scenario ID to enable
            config_override: Optional configuration overrides

        Returns:
            True if scenario was enabled successfully
        """
        with self._lock:
            if scenario_id not in self._available_scenarios:
                return False

            scenario = self._available_scenarios[scenario_id]

            # Apply config overrides if provided
            if config_override:
                # Create a copy with overrides (simplified for emulator)
                scenario.failure_config.failure_probability = config_override.get(
                    "failure_probability", scenario.failure_config.failure_probability
                )
                scenario.failure_config.error_code = config_override.get(
                    "error_code", scenario.failure_config.error_code
                )
                scenario.failure_config.error_message = config_override.get(
                    "error_message", scenario.failure_config.error_message
                )

            scenario.enabled_at = datetime.utcnow()
            self._enabled_scenarios[scenario_id] = scenario
            return True

    def disable_scenario(self, scenario_id: str) -> bool:
        """
        Disable a scenario by ID.

        Args:
            scenario_id: The scenario ID to disable

        Returns:
            True if scenario was disabled
        """
        with self._lock:
            if scenario_id in self._enabled_scenarios:
                del self._enabled_scenarios[scenario_id]
                return True
            return False

    def is_scenario_enabled(self, scenario_id: str) -> bool:
        """Check if a scenario is currently enabled."""
        with self._lock:
            return scenario_id in self._enabled_scenarios

    def get_active_scenarios(self) -> Dict[str, Scenario]:
        """Get all currently active scenarios."""
        with self._lock:
            return dict(self._enabled_scenarios)

    def get_available_scenarios(self) -> Dict[str, Scenario]:
        """Get all available scenarios."""
        return dict(self._available_scenarios)

    def reset(self) -> None:
        """Disable all scenarios."""
        with self._lock:
            self._enabled_scenarios.clear()
            self._global_stats = ScenarioStats()

    def should_inject_failure(self, service_name: str, endpoint: str = "") -> FailureResult:
        """
        Check if a failure should be injected for a request.

        Args:
            service_name: Name of the service (nova, cinder, etc.)
            endpoint: Optional endpoint path

        Returns:
            FailureResult indicating if/how the request should fail
        """
        with self._lock:
            for scenario in self._enabled_scenarios.values():
                if scenario.target_service != service_name:
                    continue

                # Check if this scenario should trigger
                if random.random() < scenario.failure_config.failure_probability:
                    # Update statistics
                    scenario.stats.times_triggered += 1
                    scenario.stats.failures_injected += 1
                    scenario.stats.last_triggered = datetime.utcnow()
                    self._global_stats.times_triggered += 1
                    self._global_stats.failures_injected += 1
                    self._global_stats.last_triggered = datetime.utcnow()

                    return FailureResult(
                        should_fail=True,
                        status_code=scenario.failure_config.error_code,
                        error_message=scenario.failure_config.error_message,
                        delay_seconds=0.0,  # Can be enhanced later
                        scenario_id=scenario.id,
                        failure_type=scenario.failure_type.value if scenario.failure_type else None,
                    )

            return FailureResult(should_fail=False)

    def get_stats(self) -> Dict[str, Any]:
        """Get scenario statistics."""
        with self._lock:
            scenario_stats = {}
            for scenario_id, scenario in self._enabled_scenarios.items():
                scenario_stats[scenario_id] = {
                    "times_triggered": scenario.stats.times_triggered,
                    "failures_injected": scenario.stats.failures_injected,
                    "last_triggered": (
                        scenario.stats.last_triggered.isoformat()
                        if scenario.stats.last_triggered
                        else None
                    ),
                }

            return {
                "global": {
                    "times_triggered": self._global_stats.times_triggered,
                    "failures_injected": self._global_stats.failures_injected,
                    "last_triggered": (
                        self._global_stats.last_triggered.isoformat()
                        if self._global_stats.last_triggered
                        else None
                    ),
                },
                "scenarios": scenario_stats,
                "enabled_count": len(self._enabled_scenarios),
            }


# Global singleton instance
simple_scenario_manager = SimpleScenarioManager()
