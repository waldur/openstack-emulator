"""Placement API endpoints for OpenStack emulator.

Implements a read-only subset of the OpenStack Placement API (microversion 1.0)
covering the calls Waldur and other clients use for scheduling/quota inspection:
list resource providers, fetch their inventories and current usages.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple

router = APIRouter()


def _require_token(auth_token: str | None) -> None:
    """Validate caller's token; raises 401 on failure."""
    validate_token_simple(auth_token, "Placement")


@router.get("/")
async def get_versions() -> dict[str, Any]:
    """Return the Placement API version document."""
    return {
        "versions": [
            {
                "id": "v1.0",
                "status": "CURRENT",
                "min_version": "1.0",
                "max_version": "1.39",
                "links": [{"rel": "self", "href": "/"}],
            }
        ]
    }


@router.get("/resource_providers")
async def list_resource_providers(
    name: str | None = Query(None),
    uuid: str | None = Query(None),
    in_tree: str | None = Query(None),
    member_of: str | None = Query(None),
    resources: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List resource providers."""
    _require_token(x_auth_token)
    providers = db.list_resource_providers(name=name, uuid=uuid)
    return {"resource_providers": [p.to_dict() for p in providers]}


@router.get("/resource_providers/{provider_uuid}")
async def get_resource_provider(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a single resource provider."""
    _require_token(x_auth_token)
    provider = db.get_resource_provider(provider_uuid)
    if provider is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return provider.to_dict()


@router.get("/resource_providers/{provider_uuid}/inventories")
async def get_provider_inventories(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get inventories (capacity per resource class) for a resource provider."""
    _require_token(x_auth_token)
    inventories = db.get_resource_provider_inventories(provider_uuid)
    if inventories is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return inventories


@router.get("/resource_providers/{provider_uuid}/usages")
async def get_provider_usages(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get current usage (per resource class) for a resource provider."""
    _require_token(x_auth_token)
    usages = db.get_resource_provider_usages(provider_uuid)
    if usages is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return usages


@router.get("/resource_providers/{provider_uuid}/aggregates")
async def get_provider_aggregates(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get aggregates associated with a resource provider (always empty in emulator)."""
    _require_token(x_auth_token)
    provider = db.get_resource_provider(provider_uuid)
    if provider is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return {
        "aggregates": [],
        "resource_provider_generation": provider.generation,
    }


@router.get("/resource_providers/{provider_uuid}/traits")
async def get_provider_traits(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get traits associated with a resource provider (always empty in emulator)."""
    _require_token(x_auth_token)
    provider = db.get_resource_provider(provider_uuid)
    if provider is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return {
        "traits": [],
        "resource_provider_generation": provider.generation,
    }


@router.get("/resource_providers/{provider_uuid}/allocations")
async def get_provider_allocations(
    provider_uuid: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get current allocations against a resource provider (stubbed empty)."""
    _require_token(x_auth_token)
    provider = db.get_resource_provider(provider_uuid)
    if provider is None:
        raise HTTPException(status_code=404, detail="No resource provider found")
    return {
        "allocations": {},
        "resource_provider_generation": provider.generation,
    }
