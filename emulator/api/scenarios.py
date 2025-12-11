"""Scenario management API endpoints for OpenStack emulator."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.scenario_manager import scenario_manager
from emulator.core.scenarios import (
    DelayDistribution,
    FailureConfig,
    FailureType,
    GradualDegradation,
    LoadProfile,
    Scenario,
    ScenarioCategory,
)

router = APIRouter(tags=["scenarios"])


# =============================================================================
# Request/Response Models
# =============================================================================


class GradualDegradationRequest(BaseModel):
    """Gradual degradation configuration."""

    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    initial_delay_ms: int = Field(default=100, alias="initialDelayMs")
    increase_per_minute_ms: int = Field(default=200, alias="increasePerMinuteMs")
    max_delay_ms: int = Field(default=30000, alias="maxDelayMs")


class LoadProfileRequest(BaseModel):
    """Load profile configuration for scenarios."""

    model_config = ConfigDict(populate_by_name=True)

    min_delay_ms: int = Field(default=0, alias="minDelayMs")
    max_delay_ms: int = Field(default=0, alias="maxDelayMs")
    distribution: str = "uniform"
    spike_probability: float = Field(default=0.0, alias="spikeProbability")
    spike_multiplier: float = Field(default=3.0, alias="spikeMultiplier")
    timeout_probability: float = Field(default=0.0, alias="timeoutProbability")
    affected_operations: list[str] = Field(default=["all"], alias="affectedOperations")
    gradual_degradation: GradualDegradationRequest | None = Field(
        default=None, alias="gradualDegradation"
    )


class FailureConfigRequest(BaseModel):
    """Failure configuration for scenarios."""

    model_config = ConfigDict(populate_by_name=True)

    failure_probability: float = Field(default=1.0, alias="failureProbability")
    error_message: str = Field(default="", alias="errorMessage")
    error_code: int = Field(default=500, alias="errorCode")
    affected_operations: list[str] = Field(default=["all"], alias="affectedOperations")
    affected_resources: list[str] = Field(default=["all"], alias="affectedResources")


class ScenarioEnableRequest(BaseModel):
    """Request to enable a scenario with optional config overrides."""

    model_config = ConfigDict(populate_by_name=True)

    load_profile: LoadProfileRequest | None = Field(default=None, alias="loadProfile")
    failure_config: FailureConfigRequest | None = Field(default=None, alias="failureConfig")


class CustomScenarioRequest(BaseModel):
    """Request to create a custom scenario."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    category: str
    failure_type: str = Field(alias="failureType")
    target_service: str | None = Field(default=None, alias="targetService")
    load_profile: LoadProfileRequest | None = Field(default=None, alias="loadProfile")
    failure_config: FailureConfigRequest | None = Field(default=None, alias="failureConfig")


class LoadPresetRequest(BaseModel):
    """Request to set system load level."""

    model_config = ConfigDict(populate_by_name=True)

    level: int = Field(ge=0, le=100, description="Load level 0-100%")
    service: str | None = Field(default=None, description="Target service (None for all)")


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/scenarios")
async def list_scenarios(
    category: str | None = Query(default=None, description="Filter by category"),
    enabled: bool = Query(default=False, description="Only show enabled scenarios"),
) -> dict[str, Any]:
    """List all available scenarios."""
    category_filter = None
    if category:
        try:
            category_filter = ScenarioCategory(category)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {category}. Valid values: {[c.value for c in ScenarioCategory]}",
            )

    scenarios = scenario_manager.list_scenarios(category=category_filter, enabled_only=enabled)

    return {
        "scenarios": [s.to_dict() for s in scenarios],
        "total": len(scenarios),
        "categories": [c.value for c in ScenarioCategory],
        "failure_types": [f.value for f in FailureType],
    }


@router.get("/scenarios/active")
async def get_active_scenarios(
    service: str | None = Query(default=None, description="Filter by target service"),
) -> dict[str, Any]:
    """Get currently active scenarios."""
    active = scenario_manager.get_active_scenarios(service)

    return {
        "active_scenarios": [s.to_dict() for s in active],
        "count": len(active),
    }


@router.get("/scenarios/stats")
async def get_scenario_stats() -> dict[str, Any]:
    """Get injection statistics for all scenarios."""
    return scenario_manager.get_stats()


@router.get("/scenarios/status")
async def get_scenario_status() -> dict[str, Any]:
    """Get overall scenario system status."""
    return scenario_manager.get_status()


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, Any]:
    """Get details of a specific scenario."""
    scenario = scenario_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {scenario_id}",
        )

    return {"scenario": scenario.to_dict()}


@router.post("/scenarios/{scenario_id}/enable")
async def enable_scenario(
    scenario_id: str,
    request: ScenarioEnableRequest | None = None,
) -> dict[str, Any]:
    """Enable a scenario, optionally with config overrides."""
    config_override = None
    if request:
        config_override = {}
        if request.load_profile:
            lp = request.load_profile
            grad_deg = {}
            if lp.gradual_degradation:
                grad_deg = {
                    "enabled": lp.gradual_degradation.enabled,
                    "initial_delay_ms": lp.gradual_degradation.initial_delay_ms,
                    "increase_per_minute_ms": lp.gradual_degradation.increase_per_minute_ms,
                    "max_delay_ms": lp.gradual_degradation.max_delay_ms,
                }
            config_override["load_profile"] = {
                "min_delay_ms": lp.min_delay_ms,
                "max_delay_ms": lp.max_delay_ms,
                "distribution": lp.distribution,
                "spike_probability": lp.spike_probability,
                "spike_multiplier": lp.spike_multiplier,
                "timeout_probability": lp.timeout_probability,
                "affected_operations": lp.affected_operations,
                "gradual_degradation": grad_deg,
            }
        if request.failure_config:
            fc = request.failure_config
            config_override["failure_config"] = {
                "failure_probability": fc.failure_probability,
                "error_message": fc.error_message,
                "error_code": fc.error_code,
                "affected_operations": fc.affected_operations,
                "affected_resources": fc.affected_resources,
            }

    scenario = scenario_manager.enable_scenario(scenario_id, config_override)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {scenario_id}",
        )

    return {
        "message": f"Scenario '{scenario.name}' enabled",
        "scenario": scenario.to_dict(),
    }


@router.post("/scenarios/{scenario_id}/disable")
async def disable_scenario(scenario_id: str) -> dict[str, Any]:
    """Disable a scenario."""
    scenario = scenario_manager.disable_scenario(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {scenario_id}",
        )

    return {
        "message": f"Scenario '{scenario.name}' disabled",
        "scenario": scenario.to_dict(),
    }


@router.post("/scenarios/reset")
async def reset_all_scenarios() -> dict[str, Any]:
    """Disable all scenarios and reset statistics."""
    scenario_manager.reset()
    return {
        "message": "All scenarios disabled and statistics reset",
        "status": scenario_manager.get_status(),
    }


@router.post("/scenarios/custom")
async def create_custom_scenario(
    request: CustomScenarioRequest,
) -> dict[str, Any]:
    """Create a custom scenario."""
    # Validate category
    try:
        category = ScenarioCategory(request.category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {request.category}",
        )

    # Validate failure type
    try:
        failure_type = FailureType(request.failure_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid failure_type: {request.failure_type}",
        )

    # Check if ID already exists
    if scenario_manager.get_scenario(request.id):
        raise HTTPException(
            status_code=409,
            detail=f"Scenario with ID '{request.id}' already exists",
        )

    # Build load profile
    load_profile = LoadProfile()
    if request.load_profile:
        lp = request.load_profile
        grad_deg = GradualDegradation()
        if lp.gradual_degradation:
            grad_deg = GradualDegradation(
                enabled=lp.gradual_degradation.enabled,
                initial_delay_ms=lp.gradual_degradation.initial_delay_ms,
                increase_per_minute_ms=lp.gradual_degradation.increase_per_minute_ms,
                max_delay_ms=lp.gradual_degradation.max_delay_ms,
            )
        load_profile = LoadProfile(
            min_delay_ms=lp.min_delay_ms,
            max_delay_ms=lp.max_delay_ms,
            distribution=DelayDistribution(lp.distribution),
            spike_probability=lp.spike_probability,
            spike_multiplier=lp.spike_multiplier,
            timeout_probability=lp.timeout_probability,
            affected_operations=lp.affected_operations,
            gradual_degradation=grad_deg,
        )

    # Build failure config
    failure_config = FailureConfig()
    if request.failure_config:
        fc = request.failure_config
        failure_config = FailureConfig(
            failure_probability=fc.failure_probability,
            error_message=fc.error_message,
            error_code=fc.error_code,
            affected_operations=fc.affected_operations,
            affected_resources=fc.affected_resources,
        )

    scenario = Scenario(
        id=request.id,
        name=request.name,
        description=request.description,
        category=category,
        failure_type=failure_type,
        target_service=request.target_service,
        load_profile=load_profile,
        failure_config=failure_config,
        builtin=False,
    )

    scenario_manager.register_scenario(scenario)

    return {
        "message": f"Custom scenario '{scenario.name}' created",
        "scenario": scenario.to_dict(),
    }


@router.delete("/scenarios/custom/{scenario_id}")
async def delete_custom_scenario(scenario_id: str) -> dict[str, Any]:
    """Delete a custom scenario. Built-in scenarios cannot be deleted."""
    scenario = scenario_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {scenario_id}",
        )

    if scenario.builtin:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in scenarios",
        )

    scenario_manager.unregister_scenario(scenario_id)

    return {
        "message": f"Custom scenario '{scenario.name}' deleted",
    }


@router.post("/scenarios/preset/{preset_name}")
async def apply_preset(
    preset_name: str,
) -> dict[str, Any]:
    """
    Apply a scenario preset (enables multiple related scenarios).

    Available presets:
    - healthy: Reset all scenarios (clean state)
    - degraded: Light performance issues + slow database
    - storage_crisis: Storage backend issues + disk full errors
    - network_trouble: Network partition + slow networking
    - overloaded: Heavy load + message queue issues + slow database
    - meltdown: Complete infrastructure failure (chaos mode)
    """
    # Define preset combinations
    preset_configs: dict[str, dict[str, Any]] = {
        "healthy": {
            "description": "All systems nominal",
            "scenarios": [],  # Empty list means reset all
        },
        "degraded": {
            "description": "Degraded performance - slow responses",
            "scenarios": ["light_load", "database_slow"],
        },
        "storage_crisis": {
            "description": "Storage infrastructure problems",
            "scenarios": ["slow_storage_backend", "cinder_disk_full", "cinder_slow"],
        },
        "network_trouble": {
            "description": "Network infrastructure issues",
            "scenarios": ["neutron_network_partition", "neutron_slow"],
        },
        "overloaded": {
            "description": "System overload - multiple bottlenecks",
            "scenarios": ["heavy_load", "rabbitmq_unstable", "database_slow"],
        },
        "meltdown": {
            "description": "Complete infrastructure meltdown",
            "scenarios": [
                "cascading_failure",
                "rabbitmq_down",
                "quota_exceeded",
                "keystone_overloaded",
            ],
        },
    }

    if preset_name not in preset_configs:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown preset: {preset_name}. Available: {list(preset_configs.keys())}",
        )

    config = preset_configs[preset_name]

    # First, disable all currently active scenarios
    scenario_manager.reset()

    # Enable the preset's scenarios
    enabled_scenarios = []
    for scenario_id in config["scenarios"]:
        scenario = scenario_manager.enable_scenario(scenario_id)
        if scenario:
            enabled_scenarios.append(scenario.to_dict())

    return {
        "message": f"Preset '{preset_name}' applied: {config['description']}",
        "preset": preset_name,
        "description": config["description"],
        "enabled_scenarios": enabled_scenarios,
        "count": len(enabled_scenarios),
    }


@router.post("/scenarios/load")
async def set_load_level(request: LoadPresetRequest) -> dict[str, Any]:
    """
    Set system load level as a percentage (0-100).

    This creates/updates a custom scenario with appropriate delays:
    - 0%: No delay
    - 25%: Light load (100-500ms)
    - 50%: Moderate load (500-2000ms)
    - 75%: Heavy load (1000-5000ms)
    - 100%: Maximum load (2000-10000ms with timeouts)
    """
    level = request.level

    # Disable existing load level scenario
    scenario_id = f"load_level_{request.service or 'all'}"
    scenario_manager.disable_scenario(scenario_id)

    if level == 0:
        return {
            "message": "Load level set to 0% (no delay)",
            "level": level,
        }

    # Calculate delays based on level
    min_delay = int(level * 20)  # 0-2000ms
    max_delay = int(level * 100)  # 0-10000ms
    timeout_prob = max(0, (level - 80) / 100)  # Timeouts only above 80%
    spike_prob = level / 200  # 0-50% spike probability

    # Create or update the load level scenario
    existing = scenario_manager.get_scenario(scenario_id)
    if existing:
        scenario_manager.unregister_scenario(scenario_id)

    scenario = Scenario(
        id=scenario_id,
        name=f"Load Level {level}%",
        description=f"System load at {level}%",
        category=ScenarioCategory.PERFORMANCE,
        failure_type=FailureType.SLOW_RESPONSE,
        target_service=request.service,
        load_profile=LoadProfile(
            min_delay_ms=min_delay,
            max_delay_ms=max_delay,
            distribution=DelayDistribution.NORMAL,
            spike_probability=spike_prob,
            spike_multiplier=2.0,
            timeout_probability=timeout_prob,
        ),
        builtin=False,
    )

    scenario_manager.register_scenario(scenario)
    scenario_manager.enable_scenario(scenario_id)

    return {
        "message": f"Load level set to {level}%",
        "level": level,
        "scenario": scenario.to_dict(),
        "target_service": request.service,
    }
