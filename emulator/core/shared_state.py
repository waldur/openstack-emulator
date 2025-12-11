"""Shared state management for cross-process scenario synchronization.

This module provides file-based state sharing between the scenario management
service and the individual OpenStack service processes (nova, keystone, etc.).
"""

import fcntl
import json
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Default state file location
DEFAULT_STATE_FILE = Path(tempfile.gettempdir()) / "openstack-emulator-scenarios.json"

# Cache TTL in seconds - how often to re-read the state file
CACHE_TTL_SECONDS = 0.5


@dataclass
class CachedState:
    """Cached scenario state with timestamp."""

    data: dict[str, Any]
    loaded_at: float


class SharedStateManager:
    """
    Manages shared scenario state via file-based persistence.

    This allows the scenario management service (port 8999) to write state
    that other service processes (nova, keystone, etc.) can read.
    """

    def __init__(self, state_file: Path | str | None = None) -> None:
        """
        Initialize the shared state manager.

        Args:
            state_file: Path to the state file. Defaults to temp directory.
        """
        self._state_file = Path(state_file) if state_file else DEFAULT_STATE_FILE
        self._cache: CachedState | None = None
        self._ensure_state_file()

    def _ensure_state_file(self) -> None:
        """Ensure the state file exists with default content."""
        if not self._state_file.exists():
            self._write_state({"enabled_scenarios": {}, "version": 1})

    def _read_state_from_file(self) -> dict[str, Any]:
        """Read state from file with locking."""
        try:
            with open(self._state_file, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                try:
                    content = f.read()
                    if not content:
                        return {"enabled_scenarios": {}, "version": 1}
                    return cast(dict[str, Any], json.loads(content))
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"enabled_scenarios": {}, "version": 1}

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state to file with locking."""
        # Ensure parent directory exists
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self._state_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
            try:
                json.dump(state, f, indent=2, default=str)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Invalidate cache after write
        self._cache = None

    def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Get current state, using cache if valid.

        Args:
            force_refresh: If True, bypass cache and read from file.

        Returns:
            Current state dictionary.
        """
        now = time.time()

        # Check cache validity
        if not force_refresh and self._cache is not None:
            if now - self._cache.loaded_at < CACHE_TTL_SECONDS:
                return self._cache.data

        # Read from file and update cache
        data = self._read_state_from_file()
        self._cache = CachedState(data=data, loaded_at=now)
        return data

    def get_enabled_scenarios(self) -> dict[str, dict[str, Any]]:
        """Get dictionary of enabled scenario IDs and their config overrides."""
        state = self.get_state()
        return cast(dict[str, dict[str, Any]], state.get("enabled_scenarios", {}))

    def is_scenario_enabled(self, scenario_id: str) -> bool:
        """Check if a specific scenario is enabled."""
        return scenario_id in self.get_enabled_scenarios()

    def enable_scenario(
        self,
        scenario_id: str,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        """
        Mark a scenario as enabled in shared state.

        Args:
            scenario_id: The scenario ID to enable.
            config_override: Optional configuration overrides.
        """
        state = self.get_state(force_refresh=True)
        enabled = state.get("enabled_scenarios", {})
        enabled[scenario_id] = {
            "enabled_at": datetime.utcnow().isoformat(),
            "config_override": config_override or {},
        }
        state["enabled_scenarios"] = enabled
        self._write_state(state)

    def disable_scenario(self, scenario_id: str) -> None:
        """Mark a scenario as disabled in shared state."""
        state = self.get_state(force_refresh=True)
        enabled = state.get("enabled_scenarios", {})
        if scenario_id in enabled:
            del enabled[scenario_id]
            state["enabled_scenarios"] = enabled
            self._write_state(state)

    def reset(self) -> None:
        """Disable all scenarios."""
        self._write_state({"enabled_scenarios": {}, "version": 1})

    def get_state_file_path(self) -> str:
        """Return the path to the state file (for debugging)."""
        return str(self._state_file)


# Global singleton instance
shared_state = SharedStateManager()
