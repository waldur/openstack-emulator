"""REST API for managing resource presets."""

from typing import Any

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from emulator.core.database import db
from emulator.core.presets import PresetLoader

router = APIRouter(prefix="/presets", tags=["presets"])


class PresetLoadRequest(BaseModel):
    """Request body for loading a preset from inline config."""

    config: dict[str, Any]


@router.get("")
async def list_presets() -> dict[str, Any]:
    """
    List all available built-in presets.

    Returns a list of preset names and descriptions.
    """
    loader = PresetLoader(db)
    presets = loader.list_available_presets()
    return {
        "presets": presets,
        "count": len(presets),
        "preset_directory": str(loader.BUILTIN_PRESETS_DIR),
    }


@router.post("/{preset_name}")
async def load_preset_by_name(preset_name: str) -> dict[str, Any]:
    """
    Load a built-in preset by name.

    This will create all resources defined in the preset.
    Resources that already exist will be skipped.
    """
    loader = PresetLoader(db)
    result = loader.load_preset_by_name(preset_name)

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Failed to load preset '{preset_name}'",
                "errors": result.errors,
            },
        )

    return {
        "message": f"Preset '{preset_name}' loaded successfully",
        "preset_name": result.preset_name,
        "resources_created": result.resources_created,
        "total_resources": result.resource_count,
        "errors": result.errors,
    }


@router.post("/load/inline")
async def load_preset_inline(request: PresetLoadRequest) -> dict[str, Any]:
    """
    Load a preset from inline configuration.

    Accepts a full preset configuration as JSON in the request body.
    """
    loader = PresetLoader(db)
    result = loader.load_preset_from_dict(request.config)

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Failed to load preset '{result.preset_name}'",
                "errors": result.errors,
            },
        )

    return {
        "message": f"Preset '{result.preset_name}' loaded successfully",
        "preset_name": result.preset_name,
        "resources_created": result.resources_created,
        "total_resources": result.resource_count,
        "errors": result.errors,
    }


@router.get("/{preset_name}/preview")
async def preview_preset(preset_name: str) -> dict[str, Any]:
    """
    Preview a preset without loading it.

    Returns the preset configuration without creating any resources.
    """
    loader = PresetLoader(db)
    preset_path = loader.BUILTIN_PRESETS_DIR / f"{preset_name}.yaml"

    if not preset_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_name}' not found",
        )

    with open(preset_path) as f:
        config = yaml.safe_load(f)

    # Count resources
    resource_counts = {}
    if "keystone" in config:
        resource_counts["projects"] = len(config["keystone"].get("projects", []))
    if "glance" in config:
        resource_counts["images"] = len(config["glance"].get("images", []))
    if "neutron" in config:
        neutron = config["neutron"]
        resource_counts["networks"] = len(neutron.get("networks", []))
        resource_counts["routers"] = len(neutron.get("routers", []))
        resource_counts["security_groups"] = len(neutron.get("security_groups", []))
    if "nova" in config:
        resource_counts["servers"] = len(config["nova"].get("servers", []))
        resource_counts["keypairs"] = len(config["nova"].get("keypairs", []))
    if "cinder" in config:
        resource_counts["volumes"] = len(config["cinder"].get("volumes", []))
        resource_counts["snapshots"] = len(config["cinder"].get("snapshots", []))
    if "octavia" in config:
        resource_counts["load_balancers"] = len(config["octavia"].get("load_balancers", []))

    return {
        "preset_name": config.get("name", preset_name),
        "description": config.get("description", ""),
        "resource_counts": resource_counts,
        "config": config,
    }
