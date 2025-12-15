"""Cinder Block Storage API endpoints for OpenStack emulator."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple

router = APIRouter(tags=["block-storage"])


# Request/Response models
class VolumeCreateRequest(BaseModel):
    """Volume creation request body."""

    name: str | None = None
    description: str | None = None
    size: int
    volume_type: str | None = None
    availability_zone: str | None = None
    metadata: dict[str, str] | None = None
    source_volid: str | None = None
    snapshot_id: str | None = None
    imageRef: str | None = None
    multiattach: bool = False


class VolumeCreateBody(BaseModel):
    """Wrapper for volume creation request."""

    volume: VolumeCreateRequest


class VolumeUpdateRequest(BaseModel):
    """Volume update request body."""

    name: str | None = None
    description: str | None = None
    metadata: dict[str, str] | None = None


class VolumeUpdateBody(BaseModel):
    """Wrapper for volume update request."""

    volume: VolumeUpdateRequest


class VolumeExtendRequest(BaseModel):
    """Volume extend request body."""

    new_size: int


class VolumeExtendBody(BaseModel):
    """Wrapper for volume extend request."""

    model_config = ConfigDict(populate_by_name=True)

    os_extend: VolumeExtendRequest = Field(..., alias="os-extend")


class VolumeAttachRequest(BaseModel):
    """Volume attach request body."""

    instance_uuid: str
    mountpoint: str | None = None
    host_name: str | None = None


class VolumeAttachBody(BaseModel):
    """Wrapper for volume attach request."""

    model_config = ConfigDict(populate_by_name=True)

    os_attach: VolumeAttachRequest = Field(..., alias="os-attach")


class VolumeDetachRequest(BaseModel):
    """Volume detach request body."""

    attachment_id: str | None = None


class VolumeDetachBody(BaseModel):
    """Wrapper for volume detach request."""

    model_config = ConfigDict(populate_by_name=True)

    os_detach: VolumeDetachRequest = Field(..., alias="os-detach")


class VolumeBootableRequest(BaseModel):
    """Volume bootable flag request."""

    bootable: bool


class VolumeBootableBody(BaseModel):
    """Wrapper for volume bootable request."""

    model_config = ConfigDict(populate_by_name=True)

    os_set_bootable: VolumeBootableRequest = Field(..., alias="os-set_bootable")


class SnapshotCreateRequest(BaseModel):
    """Snapshot creation request body."""

    name: str | None = None
    description: str | None = None
    volume_id: str
    metadata: dict[str, str] | None = None
    force: bool = False


class SnapshotCreateBody(BaseModel):
    """Wrapper for snapshot creation request."""

    snapshot: SnapshotCreateRequest


class SnapshotUpdateRequest(BaseModel):
    """Snapshot update request body."""

    name: str | None = None
    description: str | None = None


class SnapshotUpdateBody(BaseModel):
    """Wrapper for snapshot update request."""

    snapshot: SnapshotUpdateRequest


class VolumeTypeCreateRequest(BaseModel):
    """Volume type creation request body."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    is_public: bool = Field(default=True, alias="os-volume-type-access:is_public")
    extra_specs: dict[str, str] | None = None


class VolumeTypeCreateBody(BaseModel):
    """Wrapper for volume type creation request."""

    volume_type: VolumeTypeCreateRequest


class VolumeTypeUpdateRequest(BaseModel):
    """Volume type update request body."""

    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class VolumeTypeUpdateBody(BaseModel):
    """Wrapper for volume type update request."""

    volume_type: VolumeTypeUpdateRequest


class ExtraSpecsBody(BaseModel):
    """Extra specs request body."""

    extra_specs: dict[str, str]


# Helper function to validate tokens
def get_token_or_raise(auth_token: str | None) -> Any:
    """Validate token using shared database."""
    return validate_token_simple(auth_token, "Cinder")


def _parse_is_public(value: str | None) -> bool | None:
    """Parse is_public query parameter.

    Handles 'None' as a string, boolean strings, and None values.
    """
    if value is None or value == "None":
        return None
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    return None


# API Version endpoints
@router.get("/v3")
@router.get("/v3/")
async def get_version_v3(request: Request) -> dict[str, Any]:
    """Get Block Storage API v3 details."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "versions": [
            {
                "id": "v3.0",
                "status": "CURRENT",
                "version": "3.70",
                "min_version": "3.0",
                "updated": "2023-03-01T00:00:00Z",
                "links": [{"rel": "self", "href": f"{base_url}/v3/"}],
                "media-types": [
                    {
                        "base": "application/json",
                        "type": "application/vnd.openstack.volume+json;version=3",
                    }
                ],
            }
        ]
    }


# Volume endpoints
@router.get("/v3/{project_id}/volumes")
async def list_volumes(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    status: str | None = Query(None),
    name: str | None = Query(None),
    limit: int | None = Query(None),
    marker: str | None = Query(None),
    all_tenants: bool = Query(False),
) -> dict[str, Any]:
    """List volumes (summary)."""
    token = get_token_or_raise(x_auth_token)
    volumes = db.list_volumes(
        project_id=project_id if not all_tenants else None,
        status=status,
        name=name,
        limit=limit,
        marker=marker,
        all_tenants=all_tenants,
    )
    return {"volumes": [v.to_dict(detailed=False) for v in volumes]}


@router.get("/v3/{project_id}/volumes/detail")
async def list_volumes_detail(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    status: str | None = Query(None),
    name: str | None = Query(None),
    limit: int | None = Query(None),
    marker: str | None = Query(None),
    all_tenants: bool = Query(False),
) -> dict[str, Any]:
    """List volumes (detailed)."""
    token = get_token_or_raise(x_auth_token)
    volumes = db.list_volumes(
        project_id=project_id if not all_tenants else None,
        status=status,
        name=name,
        limit=limit,
        marker=marker,
        all_tenants=all_tenants,
    )
    return {"volumes": [v.to_dict(detailed=True) for v in volumes]}


@router.post("/v3/{project_id}/volumes", status_code=202)
async def create_volume(
    project_id: str,
    body: VolumeCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new volume."""
    token = get_token_or_raise(x_auth_token)
    req = body.volume

    volume = db.create_volume(
        name=req.name or "",
        size=req.size,
        project_id=project_id,
        user_id=token.user_id,
        description=req.description or "",
        volume_type=req.volume_type,
        availability_zone=req.availability_zone or "nova",
        metadata=req.metadata,
        source_volid=req.source_volid,
        snapshot_id=req.snapshot_id,
        image_id=req.imageRef,
        multiattach=req.multiattach,
    )

    return {"volume": volume.to_dict()}


@router.get("/v3/{project_id}/volumes/{volume_id}")
async def show_volume(
    project_id: str,
    volume_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Show volume details."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return {"volume": volume.to_dict()}


@router.put("/v3/{project_id}/volumes/{volume_id}")
async def update_volume(
    project_id: str,
    volume_id: str,
    body: VolumeUpdateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a volume."""
    get_token_or_raise(x_auth_token)  # Validate token
    req = body.volume

    volume = db.update_volume(
        volume_id=volume_id,
        project_id=project_id,
        name=req.name,
        description=req.description,
        metadata=req.metadata,
    )
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return {"volume": volume.to_dict()}


@router.delete("/v3/{project_id}/volumes/{volume_id}", status_code=202)
async def delete_volume(
    project_id: str,
    volume_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    force: bool = Query(False),
) -> Response:
    """Delete a volume."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    if not db.delete_volume(volume_id, project_id=project_id):
        raise HTTPException(
            status_code=400,
            detail="Volume cannot be deleted while in-use or attached",
        )
    return Response(status_code=202)


@router.post("/v3/{project_id}/volumes/{volume_id}/action", status_code=202, response_model=None)
async def volume_action(
    project_id: str,
    volume_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response | dict[str, Any]:
    """Perform an action on a volume."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    body = await request.json()

    # Handle os-extend
    if "os-extend" in body:
        new_size = body["os-extend"].get("new_size")
        if not new_size or new_size <= volume.size:
            raise HTTPException(
                status_code=400,
                detail="New size must be greater than current size",
            )
        result = db.extend_volume(volume_id, new_size, project_id=project_id)
        if not result:
            raise HTTPException(status_code=400, detail="Volume cannot be extended")
        return Response(status_code=202)

    # Handle os-attach
    if "os-attach" in body:
        attach_data = body["os-attach"]
        instance_uuid = attach_data.get("instance_uuid")
        mountpoint = attach_data.get("mountpoint", "/dev/vdb")
        host_name = attach_data.get("host_name", "compute-host-1")

        if not instance_uuid:
            raise HTTPException(status_code=400, detail="instance_uuid is required")

        attachment = db.attach_volume(
            volume_id=volume_id,
            server_id=instance_uuid,
            project_id=project_id,
            device=mountpoint,
            host_name=host_name,
        )
        if not attachment:
            raise HTTPException(status_code=400, detail="Volume cannot be attached")
        return Response(status_code=202)

    # Handle os-detach
    if "os-detach" in body:
        detach_data = body["os-detach"]
        attachment_id = detach_data.get("attachment_id")

        if attachment_id:
            if not db.detach_volume(volume_id, attachment_id, project_id=project_id):
                raise HTTPException(status_code=400, detail="Attachment not found")
        else:
            # Detach all
            for attachment in volume.attachments[:]:
                db.detach_volume(volume_id, attachment.id, project_id=project_id)
        return Response(status_code=202)

    # Handle os-set_bootable
    if "os-set_bootable" in body:
        bootable = body["os-set_bootable"].get("bootable", False)
        # Convert string to bool if needed
        if isinstance(bootable, str):
            bootable = bootable.lower() in ("true", "1", "yes")
        db.set_volume_bootable(volume_id, bootable, project_id=project_id)
        return Response(status_code=200)

    # Handle os-reset_status (admin action)
    if "os-reset_status" in body:
        # For emulator, just accept the request
        return Response(status_code=202)

    # Handle os-force_delete
    if "os-force_delete" in body:
        db.delete_volume(volume_id, project_id=project_id)
        return Response(status_code=202)

    raise HTTPException(status_code=400, detail="Unknown action")


# Snapshot endpoints
@router.get("/v3/{project_id}/snapshots")
async def list_snapshots(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    status: str | None = Query(None),
    volume_id: str | None = Query(None),
    name: str | None = Query(None),
    limit: int | None = Query(None),
    marker: str | None = Query(None),
    all_tenants: bool = Query(False),
) -> dict[str, Any]:
    """List snapshots (summary)."""
    get_token_or_raise(x_auth_token)  # Validate token
    snapshots = db.list_snapshots(
        project_id=project_id if not all_tenants else None,
        volume_id=volume_id,
        status=status,
        name=name,
        limit=limit,
        marker=marker,
        all_tenants=all_tenants,
    )
    return {"snapshots": [s.to_dict(detailed=False) for s in snapshots]}


@router.get("/v3/{project_id}/snapshots/detail")
async def list_snapshots_detail(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    status: str | None = Query(None),
    volume_id: str | None = Query(None),
    name: str | None = Query(None),
    limit: int | None = Query(None),
    marker: str | None = Query(None),
    all_tenants: bool = Query(False),
) -> dict[str, Any]:
    """List snapshots (detailed)."""
    get_token_or_raise(x_auth_token)  # Validate token
    snapshots = db.list_snapshots(
        project_id=project_id if not all_tenants else None,
        volume_id=volume_id,
        status=status,
        name=name,
        limit=limit,
        marker=marker,
        all_tenants=all_tenants,
    )
    return {"snapshots": [s.to_dict(detailed=True) for s in snapshots]}


@router.post("/v3/{project_id}/snapshots", status_code=202)
async def create_snapshot(
    project_id: str,
    body: SnapshotCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new snapshot."""
    token = get_token_or_raise(x_auth_token)
    req = body.snapshot

    snapshot = db.create_snapshot(
        volume_id=req.volume_id,
        name=req.name or "",
        project_id=project_id,
        user_id=token.user_id,
        description=req.description or "",
        metadata=req.metadata,
        force=req.force,
    )

    if not snapshot:
        raise HTTPException(
            status_code=400,
            detail="Cannot create snapshot. Volume not found or in invalid state.",
        )

    return {"snapshot": snapshot.to_dict()}


@router.get("/v3/{project_id}/snapshots/{snapshot_id}")
async def show_snapshot(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Show snapshot details."""
    get_token_or_raise(x_auth_token)  # Validate token
    snapshot = db.get_snapshot(snapshot_id, project_id=project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"snapshot": snapshot.to_dict()}


@router.put("/v3/{project_id}/snapshots/{snapshot_id}")
async def update_snapshot(
    project_id: str,
    snapshot_id: str,
    body: SnapshotUpdateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a snapshot."""
    get_token_or_raise(x_auth_token)  # Validate token
    req = body.snapshot

    snapshot = db.update_snapshot(
        snapshot_id=snapshot_id,
        project_id=project_id,
        name=req.name,
        description=req.description,
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"snapshot": snapshot.to_dict()}


@router.delete("/v3/{project_id}/snapshots/{snapshot_id}", status_code=202)
async def delete_snapshot(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a snapshot."""
    get_token_or_raise(x_auth_token)  # Validate token
    if not db.get_snapshot(snapshot_id, project_id=project_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    db.delete_snapshot(snapshot_id, project_id=project_id)
    return Response(status_code=202)


# Snapshot metadata
@router.get("/v3/{project_id}/snapshots/{snapshot_id}/metadata")
async def list_snapshot_metadata(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List snapshot metadata."""
    get_token_or_raise(x_auth_token)  # Validate token
    snapshot = db.get_snapshot(snapshot_id, project_id=project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"metadata": snapshot.metadata}


@router.put("/v3/{project_id}/snapshots/{snapshot_id}/metadata")
async def update_snapshot_metadata(
    project_id: str,
    snapshot_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update snapshot metadata."""
    get_token_or_raise(x_auth_token)  # Validate token
    body = await request.json()
    metadata = body.get("metadata", {})

    snapshot = db.update_snapshot(
        snapshot_id=snapshot_id, project_id=project_id, metadata=metadata
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"metadata": snapshot.metadata}


# Volume type endpoints
@router.get("/v3/{project_id}/types")
async def list_volume_types(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    is_public: str | None = Query(None),
) -> dict[str, Any]:
    """List volume types."""
    get_token_or_raise(x_auth_token)
    parsed_is_public = _parse_is_public(is_public)
    volume_types = db.list_volume_types(is_public=parsed_is_public)
    return {"volume_types": [vt.to_dict() for vt in volume_types]}


@router.post("/v3/{project_id}/types", status_code=200)
async def create_volume_type(
    project_id: str,
    body: VolumeTypeCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new volume type."""
    get_token_or_raise(x_auth_token)
    req = body.volume_type

    # Check if volume type with same name exists
    existing = db.get_volume_type_by_name(req.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Volume type {req.name} already exists",
        )

    vtype = db.create_volume_type(
        name=req.name,
        description=req.description or "",
        is_public=req.is_public,
        extra_specs=req.extra_specs,
    )

    return {"volume_type": vtype.to_dict()}


@router.get("/v3/{project_id}/types/{volume_type_id}")
async def show_volume_type(
    project_id: str,
    volume_type_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Show volume type details."""
    get_token_or_raise(x_auth_token)
    vtype = db.get_volume_type(volume_type_id)
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    return {"volume_type": vtype.to_dict()}


@router.put("/v3/{project_id}/types/{volume_type_id}")
async def update_volume_type(
    project_id: str,
    volume_type_id: str,
    body: VolumeTypeUpdateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a volume type."""
    get_token_or_raise(x_auth_token)
    req = body.volume_type

    vtype = db.update_volume_type(
        volume_type_id=volume_type_id,
        name=req.name,
        description=req.description,
        is_public=req.is_public,
    )
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    return {"volume_type": vtype.to_dict()}


@router.delete("/v3/{project_id}/types/{volume_type_id}", status_code=202)
async def delete_volume_type(
    project_id: str,
    volume_type_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a volume type."""
    get_token_or_raise(x_auth_token)
    if not db.get_volume_type(volume_type_id):
        raise HTTPException(status_code=404, detail="Volume type not found")

    db.delete_volume_type(volume_type_id)
    return Response(status_code=202)


# Volume type extra specs
@router.get("/v3/{project_id}/types/{volume_type_id}/extra_specs")
async def list_volume_type_extra_specs(
    project_id: str,
    volume_type_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume type extra specs."""
    get_token_or_raise(x_auth_token)
    vtype = db.get_volume_type(volume_type_id)
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    return {"extra_specs": vtype.extra_specs}


@router.post("/v3/{project_id}/types/{volume_type_id}/extra_specs")
async def create_volume_type_extra_specs(
    project_id: str,
    volume_type_id: str,
    body: ExtraSpecsBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create volume type extra specs."""
    get_token_or_raise(x_auth_token)

    vtype = db.set_volume_type_extra_specs(volume_type_id, body.extra_specs)
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    return {"extra_specs": vtype.extra_specs}


@router.get("/v3/{project_id}/types/{volume_type_id}/extra_specs/{key}")
async def show_volume_type_extra_spec(
    project_id: str,
    volume_type_id: str,
    key: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, str]:
    """Show a volume type extra spec."""
    get_token_or_raise(x_auth_token)
    vtype = db.get_volume_type(volume_type_id)
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    if key not in vtype.extra_specs:
        raise HTTPException(status_code=404, detail="Extra spec not found")
    return {key: vtype.extra_specs[key]}


@router.put("/v3/{project_id}/types/{volume_type_id}/extra_specs/{key}")
async def update_volume_type_extra_spec(
    project_id: str,
    volume_type_id: str,
    key: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, str]:
    """Update a volume type extra spec."""
    get_token_or_raise(x_auth_token)
    body = await request.json()

    if key not in body:
        raise HTTPException(status_code=400, detail="Key mismatch")

    vtype = db.set_volume_type_extra_specs(volume_type_id, {key: body[key]})
    if not vtype:
        raise HTTPException(status_code=404, detail="Volume type not found")
    return {key: vtype.extra_specs[key]}


@router.delete("/v3/{project_id}/types/{volume_type_id}/extra_specs/{key}")
async def delete_volume_type_extra_spec(
    project_id: str,
    volume_type_id: str,
    key: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a volume type extra spec."""
    get_token_or_raise(x_auth_token)

    if not db.delete_volume_type_extra_spec(volume_type_id, key):
        raise HTTPException(status_code=404, detail="Extra spec not found")
    return Response(status_code=202)


# Limits endpoint
@router.get("/v3/{project_id}/limits")
async def get_limits(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get volume limits for a project."""
    get_token_or_raise(x_auth_token)  # Validate token
    return db.get_volume_limits(project_id)


# Availability zones
@router.get("/v3/{project_id}/os-availability-zone")
async def list_availability_zones(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List availability zones."""
    get_token_or_raise(x_auth_token)
    return {
        "availabilityZoneInfo": [
            {
                "zoneName": "nova",
                "zoneState": {"available": True},
            }
        ]
    }


# Volume metadata
@router.get("/v3/{project_id}/volumes/{volume_id}/metadata")
async def list_volume_metadata(
    project_id: str,
    volume_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume metadata."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return {"metadata": volume.metadata}


@router.post("/v3/{project_id}/volumes/{volume_id}/metadata")
async def create_volume_metadata(
    project_id: str,
    volume_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create or replace volume metadata."""
    get_token_or_raise(x_auth_token)  # Validate token
    body = await request.json()
    metadata = body.get("metadata", {})

    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    volume.metadata.update(metadata)
    return {"metadata": volume.metadata}


@router.put("/v3/{project_id}/volumes/{volume_id}/metadata")
async def update_volume_metadata(
    project_id: str,
    volume_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update volume metadata."""
    get_token_or_raise(x_auth_token)  # Validate token
    body = await request.json()
    metadata = body.get("metadata", {})

    volume = db.update_volume(volume_id=volume_id, project_id=project_id, metadata=metadata)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    return {"metadata": volume.metadata}


@router.get("/v3/{project_id}/volumes/{volume_id}/metadata/{key}")
async def show_volume_metadata_item(
    project_id: str,
    volume_id: str,
    key: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Show a volume metadata item."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    if key not in volume.metadata:
        raise HTTPException(status_code=404, detail="Metadata key not found")
    return {"meta": {key: volume.metadata[key]}}


@router.put("/v3/{project_id}/volumes/{volume_id}/metadata/{key}")
async def update_volume_metadata_item(
    project_id: str,
    volume_id: str,
    key: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a volume metadata item."""
    get_token_or_raise(x_auth_token)  # Validate token
    body = await request.json()
    meta = body.get("meta", {})

    if key not in meta:
        raise HTTPException(status_code=400, detail="Key mismatch")

    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    volume.metadata[key] = meta[key]
    return {"meta": {key: volume.metadata[key]}}


@router.delete("/v3/{project_id}/volumes/{volume_id}/metadata/{key}")
async def delete_volume_metadata_item(
    project_id: str,
    volume_id: str,
    key: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a volume metadata item."""
    token = get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id, project_id=project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    if key not in volume.metadata:
        raise HTTPException(status_code=404, detail="Metadata key not found")

    del volume.metadata[key]
    return Response(status_code=200)


# Default volume type
@router.get("/v3/{project_id}/default-types")
async def list_default_types(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List default volume types."""
    get_token_or_raise(x_auth_token)
    default_type = db.get_volume_type_by_name("__DEFAULT__")
    if default_type:
        return {
            "default_types": [
                {
                    "project_id": project_id,
                    "volume_type_id": default_type.id,
                }
            ]
        }
    return {"default_types": []}


@router.get("/v3/{project_id}/default-types/{project_id_param}")
async def get_default_type(
    project_id: str,
    project_id_param: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get default volume type for a project."""
    get_token_or_raise(x_auth_token)
    default_type = db.get_volume_type_by_name("__DEFAULT__")
    if default_type:
        return {
            "default_type": {
                "project_id": project_id_param,
                "volume_type_id": default_type.id,
            }
        }
    raise HTTPException(status_code=404, detail="Default type not found")


# ==================== Quotas ====================


@router.get("/v3/{project_id}/os-quota-sets/{tenant_id}")
async def get_quota_set(
    project_id: str,
    tenant_id: str,
    usage: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get volume quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    quota = db.get_cinder_quota(tenant_id)

    if usage:
        quota_usage = db.get_cinder_quota_usage(tenant_id)
        return {
            "quota_set": {
                "id": tenant_id,
                "volumes": {
                    "limit": quota.volumes,
                    "in_use": quota_usage.get("volumes", 0),
                    "reserved": 0,
                },
                "snapshots": {
                    "limit": quota.snapshots,
                    "in_use": quota_usage.get("snapshots", 0),
                    "reserved": 0,
                },
                "gigabytes": {
                    "limit": quota.gigabytes,
                    "in_use": quota_usage.get("gigabytes", 0),
                    "reserved": 0,
                },
                "per_volume_gigabytes": {
                    "limit": quota.per_volume_gigabytes,
                    "in_use": 0,
                    "reserved": 0,
                },
                "backups": {
                    "limit": quota.backups,
                    "in_use": quota_usage.get("backups", 0),
                    "reserved": 0,
                },
                "backup_gigabytes": {
                    "limit": quota.backup_gigabytes,
                    "in_use": quota_usage.get("backup_gigabytes", 0),
                    "reserved": 0,
                },
                "groups": {
                    "limit": quota.groups,
                    "in_use": quota_usage.get("groups", 0),
                    "reserved": 0,
                },
            }
        }

    return {"quota_set": quota.to_dict()}


@router.put("/v3/{project_id}/os-quota-sets/{tenant_id}")
async def update_quota_set(
    project_id: str,
    tenant_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update volume quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    body = await request.json()
    quota_data = body.get("quota_set", {})

    quota = db.update_cinder_quota(
        project_id=tenant_id,
        volumes=quota_data.get("volumes"),
        snapshots=quota_data.get("snapshots"),
        gigabytes=quota_data.get("gigabytes"),
        per_volume_gigabytes=quota_data.get("per_volume_gigabytes"),
        backups=quota_data.get("backups"),
        backup_gigabytes=quota_data.get("backup_gigabytes"),
        groups=quota_data.get("groups"),
    )

    return {"quota_set": quota.to_dict()}


@router.delete("/v3/{project_id}/os-quota-sets/{tenant_id}", status_code=200)
async def delete_quota_set(
    project_id: str,
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete (reset) volume quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    db.delete_cinder_quota(tenant_id)
    return Response(status_code=200)


@router.get("/v3/{project_id}/os-quota-sets/{tenant_id}/defaults")
async def get_quota_set_defaults(
    project_id: str,
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get default volume quota set."""
    get_token_or_raise(x_auth_token)

    # Return default quota values
    from emulator.core.models import CinderQuota

    default_quota = CinderQuota(project_id=tenant_id)
    return {"quota_set": default_quota.to_dict()}


# Volume Transfers


class VolumeTransferRequest(BaseModel):
    """Volume transfer request."""

    name: str
    volume_id: str


class VolumeTransferBody(BaseModel):
    """Wrapper for volume transfer request."""

    transfer: VolumeTransferRequest


class VolumeTransferAcceptRequest(BaseModel):
    """Volume transfer accept request."""

    auth_key: str


class VolumeTransferAcceptBody(BaseModel):
    """Wrapper for volume transfer accept request."""

    accept: VolumeTransferAcceptRequest


@router.get("/v3/{project_id}/os-volume-transfer")
async def list_volume_transfers(
    project_id: str,
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume transfers."""
    get_token_or_raise(x_auth_token)  # Validate token

    transfers = db.list_volume_transfers(
        project_id=project_id if not all_tenants else None,
        all_tenants=all_tenants,
    )
    return {"transfers": [transfer.to_dict() for transfer in transfers]}


@router.get("/v3/{project_id}/os-volume-transfer/detail")
async def list_volume_transfers_detail(
    project_id: str,
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume transfers with details."""
    get_token_or_raise(x_auth_token)  # Validate token

    transfers = db.list_volume_transfers(
        project_id=project_id if not all_tenants else None,
        all_tenants=all_tenants,
    )
    return {"transfers": [transfer.to_dict() for transfer in transfers]}


@router.post("/v3/{project_id}/os-volume-transfer", status_code=202)
async def create_volume_transfer(
    project_id: str,
    body: VolumeTransferBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a volume transfer."""
    get_token_or_raise(x_auth_token)  # Validate token

    try:
        transfer = db.create_volume_transfer(
            name=body.transfer.name,
            volume_id=body.transfer.volume_id,
            project_id=project_id,
        )
        return {"transfer": transfer.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/v3/{project_id}/os-volume-transfer/{transfer_id}")
async def get_volume_transfer(
    project_id: str,
    transfer_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a volume transfer by ID."""
    get_token_or_raise(x_auth_token)  # Validate token

    transfer = db.get_volume_transfer(transfer_id, project_id=project_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Volume transfer not found")

    return {"transfer": transfer.to_dict()}


@router.post("/v3/{project_id}/os-volume-transfer/{transfer_id}/accept", status_code=202)
async def accept_volume_transfer(
    project_id: str,
    transfer_id: str,
    body: VolumeTransferAcceptBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Accept a volume transfer."""
    get_token_or_raise(x_auth_token)  # Validate token

    transfer = db.accept_volume_transfer(
        transfer_id=transfer_id,
        auth_key=body.accept.auth_key,
        destination_project_id=project_id,
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Volume transfer not found or invalid auth key")

    return {"transfer": transfer.to_dict()}


@router.delete("/v3/{project_id}/os-volume-transfer/{transfer_id}", status_code=202)
async def delete_volume_transfer(
    project_id: str,
    transfer_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a volume transfer."""
    get_token_or_raise(x_auth_token)  # Validate token

    success = db.delete_volume_transfer(transfer_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Volume transfer not found")

    return Response(status_code=202)


# Volume Backups


class VolumeBackupRequest(BaseModel):
    """Volume backup request."""

    name: str
    volume_id: str
    description: str = ""
    container: str = "volumebackups"
    incremental: bool = False
    snapshot_id: str | None = None


class VolumeBackupBody(BaseModel):
    """Wrapper for volume backup request."""

    backup: VolumeBackupRequest


class VolumeBackupRestoreRequest(BaseModel):
    """Volume backup restore request."""

    volume_id: str | None = None
    name: str | None = None


class VolumeBackupRestoreBody(BaseModel):
    """Wrapper for volume backup restore request."""

    restore: VolumeBackupRestoreRequest


@router.get("/v3/{project_id}/backups")
async def list_volume_backups(
    project_id: str,
    volume_id: str | None = Query(None),
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume backups."""
    get_token_or_raise(x_auth_token)  # Validate token

    backups = db.list_volume_backups(
        project_id=project_id if not all_tenants else None,
        volume_id=volume_id,
        all_tenants=all_tenants,
    )
    return {"backups": [backup.to_dict() for backup in backups]}


@router.get("/v3/{project_id}/backups/detail")
async def list_volume_backups_detail(
    project_id: str,
    volume_id: str | None = Query(None),
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume backups with details."""
    get_token_or_raise(x_auth_token)  # Validate token

    backups = db.list_volume_backups(
        project_id=project_id if not all_tenants else None,
        volume_id=volume_id,
        all_tenants=all_tenants,
    )
    return {"backups": [backup.to_dict() for backup in backups]}


@router.post("/v3/{project_id}/backups", status_code=202)
async def create_volume_backup(
    project_id: str,
    body: VolumeBackupBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a volume backup."""
    token = get_token_or_raise(x_auth_token)

    try:
        backup = db.create_volume_backup(
            name=body.backup.name,
            volume_id=body.backup.volume_id,
            description=body.backup.description,
            container=body.backup.container,
            incremental=body.backup.incremental,
            snapshot_id=body.backup.snapshot_id,
            project_id=project_id,
            user_id=token.user_id,
        )
        return {"backup": backup.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/v3/{project_id}/backups/{backup_id}")
async def get_volume_backup(
    project_id: str,
    backup_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a volume backup by ID."""
    get_token_or_raise(x_auth_token)  # Validate token

    backup = db.get_volume_backup(backup_id, project_id=project_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Volume backup not found")

    return {"backup": backup.to_dict()}


@router.delete("/v3/{project_id}/backups/{backup_id}", status_code=202)
async def delete_volume_backup(
    project_id: str,
    backup_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a volume backup."""
    get_token_or_raise(x_auth_token)  # Validate token

    success = db.delete_volume_backup(backup_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Volume backup not found")

    return Response(status_code=202)


@router.post("/v3/{project_id}/backups/{backup_id}/restore", status_code=202)
async def restore_volume_backup(
    project_id: str,
    backup_id: str,
    body: VolumeBackupRestoreBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Restore a volume from backup."""
    get_token_or_raise(x_auth_token)  # Validate token

    volume = db.restore_volume_backup(
        backup_id=backup_id,
        volume_id=body.restore.volume_id,
        name=body.restore.name,
        project_id=project_id,
    )
    if not volume:
        raise HTTPException(status_code=404, detail="Volume backup not found")

    return {"restore": {"volume_id": volume.id, "backup_id": backup_id}}


# Consistency Groups


class ConsistencyGroupRequest(BaseModel):
    """Consistency group request."""

    name: str
    description: str = ""
    volume_types: list[str] = Field(default_factory=list)
    availability_zone: str = "nova"


class ConsistencyGroupBody(BaseModel):
    """Wrapper for consistency group request."""

    group: ConsistencyGroupRequest


class GroupSnapshotRequest(BaseModel):
    """Group snapshot request."""

    name: str
    description: str = ""
    group_id: str


class GroupSnapshotBody(BaseModel):
    """Wrapper for group snapshot request."""

    group_snapshot: GroupSnapshotRequest


@router.get("/v3/{project_id}/groups")
async def list_consistency_groups(
    project_id: str,
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List consistency groups."""
    get_token_or_raise(x_auth_token)  # Validate token

    groups = db.list_consistency_groups(
        project_id=project_id if not all_tenants else None,
        all_tenants=all_tenants,
    )
    return {"groups": [group.to_dict() for group in groups]}


@router.get("/v3/{project_id}/groups/detail")
async def list_consistency_groups_detail(
    project_id: str,
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List consistency groups with details."""
    get_token_or_raise(x_auth_token)  # Validate token

    groups = db.list_consistency_groups(
        project_id=project_id if not all_tenants else None,
        all_tenants=all_tenants,
    )
    return {"groups": [group.to_dict() for group in groups]}


@router.post("/v3/{project_id}/groups", status_code=202)
async def create_consistency_group(
    project_id: str,
    body: ConsistencyGroupBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a consistency group."""
    token = get_token_or_raise(x_auth_token)

    group = db.create_consistency_group(
        name=body.group.name,
        description=body.group.description,
        volume_types=body.group.volume_types,
        availability_zone=body.group.availability_zone,
        project_id=project_id,
        user_id=token.user_id,
    )
    return {"group": group.to_dict()}


@router.get("/v3/{project_id}/groups/{group_id}")
async def get_consistency_group(
    project_id: str,
    group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a consistency group by ID."""
    get_token_or_raise(x_auth_token)  # Validate token

    group = db.get_consistency_group(group_id, project_id=project_id)
    if not group:
        raise HTTPException(status_code=404, detail="Consistency group not found")

    return {"group": group.to_dict()}


@router.delete("/v3/{project_id}/groups/{group_id}", status_code=202)
async def delete_consistency_group(
    project_id: str,
    group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a consistency group."""
    get_token_or_raise(x_auth_token)  # Validate token

    success = db.delete_consistency_group(group_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Consistency group not found")

    return Response(status_code=202)


@router.get("/v3/{project_id}/group_snapshots")
async def list_group_snapshots(
    project_id: str,
    group_id: str | None = Query(None),
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List group snapshots."""
    get_token_or_raise(x_auth_token)  # Validate token

    snapshots = db.list_group_snapshots(
        project_id=project_id if not all_tenants else None,
        group_id=group_id,
        all_tenants=all_tenants,
    )
    return {"group_snapshots": [snapshot.to_dict() for snapshot in snapshots]}


@router.get("/v3/{project_id}/group_snapshots/detail")
async def list_group_snapshots_detail(
    project_id: str,
    group_id: str | None = Query(None),
    all_tenants: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List group snapshots with details."""
    get_token_or_raise(x_auth_token)  # Validate token

    snapshots = db.list_group_snapshots(
        project_id=project_id if not all_tenants else None,
        group_id=group_id,
        all_tenants=all_tenants,
    )
    return {"group_snapshots": [snapshot.to_dict() for snapshot in snapshots]}


@router.post("/v3/{project_id}/group_snapshots", status_code=202)
async def create_group_snapshot(
    project_id: str,
    body: GroupSnapshotBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a group snapshot."""
    token = get_token_or_raise(x_auth_token)

    try:
        snapshot = db.create_group_snapshot(
            name=body.group_snapshot.name,
            group_id=body.group_snapshot.group_id,
            description=body.group_snapshot.description,
            project_id=project_id,
            user_id=token.user_id,
        )
        return {"group_snapshot": snapshot.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/v3/{project_id}/group_snapshots/{snapshot_id}")
async def get_group_snapshot(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a group snapshot by ID."""
    get_token_or_raise(x_auth_token)  # Validate token

    snapshot = db.get_group_snapshot(snapshot_id, project_id=project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Group snapshot not found")

    return {"group_snapshot": snapshot.to_dict()}


@router.delete("/v3/{project_id}/group_snapshots/{snapshot_id}", status_code=202)
async def delete_group_snapshot(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a group snapshot."""
    get_token_or_raise(x_auth_token)  # Validate token

    success = db.delete_group_snapshot(snapshot_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Group snapshot not found")

    return Response(status_code=202)
