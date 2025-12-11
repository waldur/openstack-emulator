"""Scenario manager for controlling failure and load injection.

This module provides centralized scenario management with cross-process
state sharing via file-based persistence.
"""

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from emulator.core.scenarios import (
    DelayDistribution,
    FailureConfig,
    FailureType,
    LoadProfile,
    Scenario,
    ScenarioCategory,
    ScenarioStats,
    get_builtin_scenarios,
)
from emulator.core.shared_state import shared_state


@dataclass
class FailureResult:
    """Result of a failure check - indicates if/how a request should fail."""

    should_fail: bool
    status_code: int = 500
    message: str = ""
    failure_type: FailureType | None = None
    scenario_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "should_fail": self.should_fail,
            "status_code": self.status_code,
            "message": self.message,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "scenario_id": self.scenario_id,
        }


@dataclass
class DelayResult:
    """Result of a delay calculation."""

    delay_ms: int = 0
    should_timeout: bool = False
    scenario_ids: list[str] | None = None

    def __post_init__(self) -> None:
        if self.scenario_ids is None:
            self.scenario_ids = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "delay_ms": self.delay_ms,
            "should_timeout": self.should_timeout,
            "scenario_ids": self.scenario_ids,
        }


class ScenarioManager:
    """Central manager for scenario state and injection logic.

    This manager supports cross-process state sharing via file-based persistence.
    When scenarios are enabled/disabled via the API (scenarios service), the state
    is persisted to a shared file. Other service processes (nova, keystone, etc.)
    read this shared state to know which scenarios are active.
    """

    def __init__(self, is_primary: bool = False) -> None:
        """
        Initialize the scenario manager.

        Args:
            is_primary: If True, this instance writes to shared state (scenarios service).
                       If False, this instance reads from shared state (other services).
        """
        self._lock = threading.RLock()
        self._scenarios: dict[str, Scenario] = {}
        self._global_stats = ScenarioStats()
        self._is_primary = is_primary
        self._init_builtin_scenarios()

    def _init_builtin_scenarios(self) -> None:
        """Initialize built-in scenarios."""
        for scenario in get_builtin_scenarios():
            self._scenarios[scenario.id] = scenario

    def sync_from_shared_state(self) -> None:
        """
        Synchronize local state from shared file state.

        Called by middleware before processing requests to ensure
        the local scenario state matches what's in the shared file.
        """
        with self._lock:
            enabled_scenarios = shared_state.get_enabled_scenarios()

            # Update local scenarios to match shared state
            for scenario in self._scenarios.values():
                if scenario.id in enabled_scenarios:
                    if not scenario.enabled:
                        scenario.enabled = True
                        scenario.enabled_at = datetime.utcnow()
                        # Start gradual degradation timer if enabled
                        if scenario.load_profile.gradual_degradation.enabled:
                            scenario.load_profile.gradual_degradation.started_at = datetime.utcnow()
                else:
                    if scenario.enabled:
                        scenario.enabled = False
                        scenario.enabled_at = None
                        scenario.load_profile.gradual_degradation.started_at = None

    def reset(self) -> None:
        """Reset all scenarios to disabled state and clear stats."""
        with self._lock:
            for scenario in self._scenarios.values():
                scenario.enabled = False
                scenario.enabled_at = None
                scenario.stats = ScenarioStats()
                # Reset gradual degradation start time
                scenario.load_profile.gradual_degradation.started_at = None
            self._global_stats = ScenarioStats()

            # Persist to shared state
            shared_state.reset()

    def register_scenario(self, scenario: Scenario) -> Scenario:
        """Register a new scenario (custom or override builtin)."""
        with self._lock:
            scenario.builtin = False
            self._scenarios[scenario.id] = scenario
            return scenario

    def unregister_scenario(self, scenario_id: str) -> bool:
        """Unregister a custom scenario. Cannot unregister builtin scenarios."""
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if scenario and not scenario.builtin:
                del self._scenarios[scenario_id]
                return True
            return False

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        """Get a scenario by ID."""
        with self._lock:
            return self._scenarios.get(scenario_id)

    def list_scenarios(
        self,
        category: ScenarioCategory | None = None,
        enabled_only: bool = False,
    ) -> list[Scenario]:
        """List all scenarios, optionally filtered."""
        with self._lock:
            scenarios = list(self._scenarios.values())

            if category:
                scenarios = [s for s in scenarios if s.category == category]

            if enabled_only:
                scenarios = [s for s in scenarios if s.enabled]

            return sorted(scenarios, key=lambda s: (s.category.value, s.name))

    def enable_scenario(
        self,
        scenario_id: str,
        config_override: dict[str, Any] | None = None,
    ) -> Scenario | None:
        """Enable a scenario, optionally with config overrides."""
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if not scenario:
                return None

            scenario.enabled = True
            scenario.enabled_at = datetime.utcnow()

            # Apply config overrides if provided
            if config_override:
                if "load_profile" in config_override:
                    scenario.load_profile = LoadProfile.from_dict(config_override["load_profile"])
                if "failure_config" in config_override:
                    scenario.failure_config = FailureConfig.from_dict(
                        config_override["failure_config"]
                    )

            # Start gradual degradation timer if enabled
            if scenario.load_profile.gradual_degradation.enabled:
                scenario.load_profile.gradual_degradation.started_at = datetime.utcnow()

            # Persist to shared state
            shared_state.enable_scenario(scenario_id, config_override)

            return scenario

    def disable_scenario(self, scenario_id: str) -> Scenario | None:
        """Disable a scenario."""
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if not scenario:
                return None

            scenario.enabled = False
            scenario.enabled_at = None
            # Reset gradual degradation
            scenario.load_profile.gradual_degradation.started_at = None

            # Persist to shared state
            shared_state.disable_scenario(scenario_id)

            return scenario

    def get_active_scenarios(
        self,
        service: str | None = None,
    ) -> list[Scenario]:
        """Get active scenarios for a service (or all if service is None)."""
        with self._lock:
            active = [s for s in self._scenarios.values() if s.enabled]

            if service:
                # Include scenarios targeting this service OR all services (None)
                active = [
                    s for s in active if s.target_service is None or s.target_service == service
                ]

            return active

    def _calculate_delay_for_profile(
        self,
        profile: LoadProfile,
        operation: str,
    ) -> int:
        """Calculate delay in milliseconds for a load profile."""
        # Check if this operation is affected
        if "all" not in profile.affected_operations:
            if operation not in profile.affected_operations:
                return 0

        # Handle gradual degradation
        if profile.gradual_degradation.enabled:
            base_delay = profile.gradual_degradation.get_current_delay_ms()
        else:
            base_delay = self._get_distributed_delay(
                profile.min_delay_ms,
                profile.max_delay_ms,
                profile.distribution,
            )

        # Apply spike if triggered
        if profile.spike_probability > 0:
            if random.random() < profile.spike_probability:
                base_delay = int(base_delay * profile.spike_multiplier)

        return base_delay

    def _get_distributed_delay(
        self,
        min_ms: int,
        max_ms: int,
        distribution: DelayDistribution,
    ) -> int:
        """Get a delay value based on distribution type."""
        if min_ms >= max_ms:
            return min_ms

        if distribution == DelayDistribution.UNIFORM:
            return random.randint(min_ms, max_ms)

        elif distribution == DelayDistribution.NORMAL:
            # Normal distribution centered between min and max
            mean = (min_ms + max_ms) / 2
            std_dev = (max_ms - min_ms) / 4  # 95% within range
            delay = random.gauss(mean, std_dev)
            return int(max(min_ms, min(max_ms, delay)))

        elif distribution == DelayDistribution.EXPONENTIAL:
            # Exponential: most requests fast, some very slow
            # Use exponential distribution scaled to our range
            lambda_param = 3.0 / (max_ms - min_ms)  # Scale parameter
            delay = min_ms + random.expovariate(lambda_param)
            return int(min(max_ms, delay))

        return min_ms

    def calculate_delay(
        self,
        service: str | None = None,
        operation: str = "all",
    ) -> DelayResult:
        """
        Calculate total delay for a request based on active scenarios.

        Delays from multiple scenarios are stacked (additive).
        """
        with self._lock:
            active = self.get_active_scenarios(service)
            total_delay = 0
            should_timeout = False
            scenario_ids: list[str] = []

            for scenario in active:
                # Only process scenarios with slow_response failure type
                if scenario.failure_type != FailureType.SLOW_RESPONSE:
                    # But still check for timeout probability on other scenarios
                    if scenario.load_profile.timeout_probability > 0:
                        if random.random() < scenario.load_profile.timeout_probability:
                            should_timeout = True
                            scenario_ids.append(scenario.id)
                    continue

                delay = self._calculate_delay_for_profile(scenario.load_profile, operation)
                if delay > 0:
                    total_delay += delay
                    scenario_ids.append(scenario.id)

                    # Update stats
                    scenario.stats.times_triggered += 1
                    scenario.stats.total_delay_injected_ms += delay
                    scenario.stats.last_triggered = datetime.utcnow()

                # Check for timeout
                if scenario.load_profile.timeout_probability > 0:
                    if random.random() < scenario.load_profile.timeout_probability:
                        should_timeout = True
                        scenario.stats.timeouts_injected += 1

            # Update global stats
            if total_delay > 0:
                self._global_stats.times_triggered += 1
                self._global_stats.total_delay_injected_ms += total_delay
                self._global_stats.last_triggered = datetime.utcnow()

            if should_timeout:
                self._global_stats.timeouts_injected += 1

            return DelayResult(
                delay_ms=total_delay,
                should_timeout=should_timeout,
                scenario_ids=scenario_ids,
            )

    def should_fail(
        self,
        service: str | None = None,
        operation: str = "all",
        resource: str = "all",
    ) -> FailureResult | None:
        """
        Check if a request should fail based on active scenarios.

        Returns FailureResult if request should fail, None otherwise.
        """
        with self._lock:
            active = self.get_active_scenarios(service)

            for scenario in active:
                # Skip slow_response scenarios (handled by calculate_delay)
                if scenario.failure_type == FailureType.SLOW_RESPONSE:
                    continue

                config = scenario.failure_config

                # Check if this operation is affected
                if "all" not in config.affected_operations:
                    if operation not in config.affected_operations:
                        continue

                # Check if this resource is affected
                if "all" not in config.affected_resources:
                    if resource not in config.affected_resources:
                        continue

                # Check failure probability
                if random.random() > config.failure_probability:
                    continue

                # This request should fail
                scenario.stats.times_triggered += 1
                scenario.stats.failures_injected += 1
                scenario.stats.last_triggered = datetime.utcnow()

                self._global_stats.times_triggered += 1
                self._global_stats.failures_injected += 1
                self._global_stats.last_triggered = datetime.utcnow()

                return FailureResult(
                    should_fail=True,
                    status_code=config.error_code,
                    message=config.error_message
                    or f"Injected failure: {scenario.failure_type.value}",
                    failure_type=scenario.failure_type,
                    scenario_id=scenario.id,
                )

            return None

    def apply_delay(
        self,
        service: str | None = None,
        operation: str = "all",
    ) -> DelayResult:
        """
        Apply delay synchronously (blocking).

        Returns the delay result with information about what was applied.
        """
        result = self.calculate_delay(service, operation)

        if result.delay_ms > 0:
            time.sleep(result.delay_ms / 1000.0)

        return result

    async def apply_delay_async(
        self,
        service: str | None = None,
        operation: str = "all",
    ) -> DelayResult:
        """
        Apply delay asynchronously (non-blocking).

        Returns the delay result with information about what was applied.
        """
        import asyncio

        result = self.calculate_delay(service, operation)

        if result.delay_ms > 0:
            await asyncio.sleep(result.delay_ms / 1000.0)

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get global injection statistics."""
        with self._lock:
            scenario_stats = {}
            for scenario_id, scenario in self._scenarios.items():
                if scenario.enabled or scenario.stats.times_triggered > 0:
                    scenario_stats[scenario_id] = scenario.stats.to_dict()

            return {
                "global": self._global_stats.to_dict(),
                "scenarios": scenario_stats,
                "active_count": len(self.get_active_scenarios()),
            }

    def get_status(self) -> dict[str, Any]:
        """Get current scenario system status."""
        with self._lock:
            active = self.get_active_scenarios()
            return {
                "active_scenarios": [s.id for s in active],
                "active_count": len(active),
                "total_scenarios": len(self._scenarios),
                "stats": self.get_stats(),
            }


# Global singleton instance
scenario_manager = ScenarioManager()
