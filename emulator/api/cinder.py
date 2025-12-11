"""Cinder Block Storage API endpoints for OpenStack emulator."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db

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
    """Validate token or raise 401 error."""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = db.validate_token(auth_token)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return token


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
        project_id=token.project_id if not all_tenants else None,
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
        project_id=token.project_id if not all_tenants else None,
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
        project_id=token.project_id,
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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
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
    get_token_or_raise(x_auth_token)
    req = body.volume

    volume = db.update_volume(
        volume_id=volume_id,
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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    if not db.delete_volume(volume_id):
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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
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
        result = db.extend_volume(volume_id, new_size)
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
            if not db.detach_volume(volume_id, attachment_id):
                raise HTTPException(status_code=400, detail="Attachment not found")
        else:
            # Detach all
            for attachment in volume.attachments[:]:
                db.detach_volume(volume_id, attachment.id)
        return Response(status_code=202)

    # Handle os-set_bootable
    if "os-set_bootable" in body:
        bootable = body["os-set_bootable"].get("bootable", False)
        # Convert string to bool if needed
        if isinstance(bootable, str):
            bootable = bootable.lower() in ("true", "1", "yes")
        db.set_volume_bootable(volume_id, bootable)
        return Response(status_code=200)

    # Handle os-reset_status (admin action)
    if "os-reset_status" in body:
        # For emulator, just accept the request
        return Response(status_code=202)

    # Handle os-force_delete
    if "os-force_delete" in body:
        db.delete_volume(volume_id)
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
    token = get_token_or_raise(x_auth_token)
    snapshots = db.list_snapshots(
        project_id=token.project_id if not all_tenants else None,
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
    token = get_token_or_raise(x_auth_token)
    snapshots = db.list_snapshots(
        project_id=token.project_id if not all_tenants else None,
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
        project_id=token.project_id,
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
    get_token_or_raise(x_auth_token)
    snapshot = db.get_snapshot(snapshot_id)
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
    get_token_or_raise(x_auth_token)
    req = body.snapshot

    snapshot = db.update_snapshot(
        snapshot_id=snapshot_id,
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
    get_token_or_raise(x_auth_token)
    if not db.get_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    db.delete_snapshot(snapshot_id)
    return Response(status_code=202)


# Snapshot metadata
@router.get("/v3/{project_id}/snapshots/{snapshot_id}/metadata")
async def list_snapshot_metadata(
    project_id: str,
    snapshot_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List snapshot metadata."""
    get_token_or_raise(x_auth_token)
    snapshot = db.get_snapshot(snapshot_id)
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
    get_token_or_raise(x_auth_token)
    body = await request.json()
    metadata = body.get("metadata", {})

    snapshot = db.update_snapshot(snapshot_id=snapshot_id, metadata=metadata)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"metadata": snapshot.metadata}


# Volume type endpoints
@router.get("/v3/{project_id}/types")
async def list_volume_types(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    is_public: bool | None = Query(None),
) -> dict[str, Any]:
    """List volume types."""
    get_token_or_raise(x_auth_token)
    volume_types = db.list_volume_types(is_public=is_public)
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
    token = get_token_or_raise(x_auth_token)
    return db.get_volume_limits(token.project_id)


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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
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
    get_token_or_raise(x_auth_token)
    body = await request.json()
    metadata = body.get("metadata", {})

    volume = db.get_volume(volume_id)
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
    get_token_or_raise(x_auth_token)
    body = await request.json()
    metadata = body.get("metadata", {})

    volume = db.update_volume(volume_id=volume_id, metadata=metadata)
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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
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
    get_token_or_raise(x_auth_token)
    body = await request.json()
    meta = body.get("meta", {})

    if key not in meta:
        raise HTTPException(status_code=400, detail="Key mismatch")

    volume = db.get_volume(volume_id)
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
    get_token_or_raise(x_auth_token)
    volume = db.get_volume(volume_id)
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
