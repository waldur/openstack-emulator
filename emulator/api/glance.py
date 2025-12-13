"""Glance Image API v2 endpoints for OpenStack emulator.

Implements the OpenStack Glance Image Service API v2.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db
from emulator.core.models import ContainerFormat, DiskFormat, ImageVisibility
from emulator.core.simple_auth import validate_token_simple

router = APIRouter()


# Pydantic models for requests/responses
class ImageCreateRequest(BaseModel):
    """Request model for creating an image."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    visibility: str | None = None
    protected: bool = False
    min_disk: int = Field(default=0, alias="min_disk")
    min_ram: int = Field(default=0, alias="min_ram")
    container_format: str | None = None
    disk_format: str | None = None
    tags: list[str] | None = None
    architecture: str | None = None
    os_distro: str | None = None
    os_version: str | None = None


class ImageUpdateOperation(BaseModel):
    """JSON Patch operation for updating an image."""

    model_config = ConfigDict(populate_by_name=True)

    op: str
    path: str
    value: Any = None


class ImageMemberRequest(BaseModel):
    """Request model for adding an image member."""

    model_config = ConfigDict(populate_by_name=True)

    member: str


class ImageMemberUpdateRequest(BaseModel):
    """Request model for updating an image member."""

    model_config = ConfigDict(populate_by_name=True)

    status: str


# Helper functions
def _get_project_id(token: str | None) -> str:
    """Extract project ID from token."""
    if not token:
        return "admin"
    try:
        token_data = validate_token_simple(token, "Glance")
        return token_data.project_id
    except HTTPException:
        return "admin"  # Fallback for development


def _parse_visibility(visibility: str | None) -> ImageVisibility | None:
    """Parse visibility string to enum."""
    if not visibility:
        return None
    try:
        return ImageVisibility(visibility)
    except ValueError:
        return None


def _parse_container_format(fmt: str | None) -> ContainerFormat | None:
    """Parse container format string to enum."""
    if not fmt:
        return None
    try:
        return ContainerFormat(fmt)
    except ValueError:
        return None


def _parse_disk_format(fmt: str | None) -> DiskFormat | None:
    """Parse disk format string to enum."""
    if not fmt:
        return None
    try:
        return DiskFormat(fmt)
    except ValueError:
        return None


# API Version endpoint
@router.get("/")
async def get_versions() -> dict[str, Any]:
    """Get available API versions."""
    return {
        "versions": [
            {
                "id": "v2.17",
                "status": "CURRENT",
                "links": [{"rel": "self", "href": "/v2/"}],
            },
            {
                "id": "v2.0",
                "status": "SUPPORTED",
                "links": [{"rel": "self", "href": "/v2/"}],
            },
        ]
    }


# Images endpoints
@router.get("/v2/images")
async def list_images(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    limit: int | None = Query(None),
    marker: str | None = Query(None),
    name: str | None = Query(None),
    visibility: str | None = Query(None),
    member_status: str | None = Query(None),
    owner: str | None = Query(None),
    status: str | None = Query(None),
    tag: str | None = Query(None),
    sort_key: str = Query("created_at"),
    sort_dir: str = Query("desc"),
) -> dict[str, Any]:
    """List images."""
    images = db.list_glance_images(
        owner=owner,
        visibility=visibility,
        status=status,
        name=name,
        tag=tag,
        member_status=member_status,
        limit=limit,
        marker=marker,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )

    images_list = [img.to_dict() for img in images]

    result: dict[str, Any] = {
        "images": images_list,
        "schema": "/v2/schemas/images",
        "first": "/v2/images",
    }

    # Add next link if there might be more images
    if limit and len(images_list) == limit:
        result["next"] = f"/v2/images?marker={images_list[-1]['id']}&limit={limit}"

    return result


@router.post("/v2/images", status_code=201)
async def create_image(
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an image."""
    project_id = _get_project_id(x_auth_token)

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        body = {}

    name = body.get("name", "")
    visibility = _parse_visibility(body.get("visibility", "private"))
    if visibility is None:
        visibility = ImageVisibility.PRIVATE

    container_format = _parse_container_format(body.get("container_format"))
    disk_format = _parse_disk_format(body.get("disk_format"))

    image = db.create_glance_image(
        name=name,
        owner=project_id,
        visibility=visibility,
        min_disk=body.get("min_disk", 0),
        min_ram=body.get("min_ram", 0),
        protected=body.get("protected", False),
        container_format=container_format,
        disk_format=disk_format,
        tags=body.get("tags"),
        architecture=body.get("architecture"),
        os_distro=body.get("os_distro"),
        os_version=body.get("os_version"),
    )

    return image.to_dict()


@router.get("/v2/images/{image_id}")
async def get_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get image details."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return image.to_dict()


@router.patch("/v2/images/{image_id}", response_model=None)
async def update_image(
    image_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update image using JSON Patch."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.protected:
        raise HTTPException(status_code=403, detail="Image is protected")

    # Parse JSON Patch operations
    try:
        operations = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Process patch operations
    updates: dict[str, Any] = {}
    for op in operations:
        if not isinstance(op, dict):
            continue

        operation = op.get("op")
        path = op.get("path", "").lstrip("/")
        value = op.get("value")

        if operation == "replace" or operation == "add":
            if path == "name":
                updates["name"] = value
            elif path == "visibility":
                updates["visibility"] = _parse_visibility(value)
            elif path == "min_disk":
                updates["min_disk"] = value
            elif path == "min_ram":
                updates["min_ram"] = value
            elif path == "protected":
                updates["protected"] = value
            elif path == "container_format":
                updates["container_format"] = _parse_container_format(value)
            elif path == "disk_format":
                updates["disk_format"] = _parse_disk_format(value)
            elif path == "tags":
                updates["tags"] = value
            elif path == "architecture":
                updates["architecture"] = value
            elif path == "os_distro":
                updates["os_distro"] = value
            elif path == "os_version":
                updates["os_version"] = value
            else:
                # Custom property
                if "properties" not in updates:
                    updates["properties"] = {}
                updates["properties"][path] = value
        elif operation == "remove":
            if path == "tags":
                updates["tags"] = []
            # Handle other removals as needed

    updated_image = db.update_glance_image(image_id, **updates)
    if not updated_image:
        raise HTTPException(status_code=404, detail="Image not found")

    return updated_image.to_dict()


@router.delete("/v2/images/{image_id}", status_code=204, response_model=None)
async def delete_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an image."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.protected:
        raise HTTPException(status_code=403, detail="Image is protected")

    success = db.delete_glance_image(image_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete image")

    return Response(status_code=204)


# Image data (file) endpoints
@router.put("/v2/images/{image_id}/file", status_code=204, response_model=None)
async def upload_image_data(
    image_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    content_length: int | None = Header(None, alias="Content-Length"),
) -> Response:
    """Upload image data."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Simulate reading the data (for emulator, we just accept and ignore)
    # In a real implementation, we'd store the actual bytes
    body = await request.body()
    size = content_length or len(body)

    # Calculate simulated checksum
    import hashlib

    checksum = hashlib.md5(body).hexdigest() if body else "simulated"

    result = db.upload_image_data(
        image_id=image_id,
        size=size,
        checksum=checksum,
    )

    if not result:
        raise HTTPException(status_code=409, detail="Cannot upload to this image")

    return Response(status_code=204)


@router.get("/v2/images/{image_id}/file", response_model=None)
async def download_image_data(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Download image data."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.status.value != "active":
        raise HTTPException(status_code=204, detail="Image has no data")

    # Return empty data for emulator
    return Response(
        content=b"",
        media_type="application/octet-stream",
        headers={
            "Content-MD5": image.checksum or "",
            "X-Image-Meta-Checksum": image.checksum or "",
        },
    )


# Image actions
@router.post("/v2/images/{image_id}/actions/deactivate", status_code=204, response_model=None)
async def deactivate_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Deactivate an image."""
    success = db.deactivate_glance_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Image not found or cannot be deactivated")

    return Response(status_code=204)


@router.post("/v2/images/{image_id}/actions/reactivate", status_code=204, response_model=None)
async def reactivate_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Reactivate an image."""
    success = db.reactivate_glance_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Image not found or cannot be reactivated")

    return Response(status_code=204)


# Image tags
@router.put("/v2/images/{image_id}/tags/{tag}", status_code=204, response_model=None)
async def add_image_tag(
    image_id: str,
    tag: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Add a tag to an image."""
    success = db.add_image_tag(image_id, tag)
    if not success:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(status_code=204)


@router.delete("/v2/images/{image_id}/tags/{tag}", status_code=204, response_model=None)
async def delete_image_tag(
    image_id: str,
    tag: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a tag from an image."""
    success = db.delete_image_tag(image_id, tag)
    if not success:
        raise HTTPException(status_code=404, detail="Image or tag not found")

    return Response(status_code=204)


# Image members (sharing)
@router.get("/v2/images/{image_id}/members")
async def list_image_members(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List image members."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    members = db.list_image_members(image_id)
    return {
        "members": [m.to_dict() for m in members],
        "schema": "/v2/schemas/members",
    }


@router.post("/v2/images/{image_id}/members", status_code=200)
async def add_image_member(
    image_id: str,
    request: ImageMemberRequest,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Add a member to an image."""
    image = db.get_glance_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Image must be shared visibility
    if image.visibility != ImageVisibility.SHARED:
        raise HTTPException(
            status_code=403, detail="Image visibility must be 'shared' to add members"
        )

    member = db.add_image_member(image_id, request.member)
    if not member:
        raise HTTPException(status_code=409, detail="Cannot add member")

    return member.to_dict()


@router.get("/v2/images/{image_id}/members/{member_id}")
async def get_image_member(
    image_id: str,
    member_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get image member details."""
    member = db.get_image_member(image_id, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    return member.to_dict()


@router.put("/v2/images/{image_id}/members/{member_id}")
async def update_image_member(
    image_id: str,
    member_id: str,
    request: ImageMemberUpdateRequest,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update image member status."""
    member = db.update_image_member(image_id, member_id, request.status)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    return member.to_dict()


@router.delete("/v2/images/{image_id}/members/{member_id}", status_code=204, response_model=None)
async def delete_image_member(
    image_id: str,
    member_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Remove a member from an image."""
    success = db.delete_image_member(image_id, member_id)
    if not success:
        raise HTTPException(status_code=404, detail="Member not found")

    return Response(status_code=204)


# Schemas
@router.get("/v2/schemas/image")
async def get_image_schema() -> dict[str, Any]:
    """Get image schema."""
    return {
        "name": "image",
        "properties": {
            "id": {"type": "string", "description": "Image ID"},
            "name": {"type": "string", "description": "Image name"},
            "status": {"type": "string", "description": "Image status"},
            "visibility": {"type": "string", "description": "Image visibility"},
            "protected": {"type": "boolean", "description": "Protected flag"},
            "owner": {"type": "string", "description": "Owner project ID"},
            "min_disk": {"type": "integer", "description": "Minimum disk (GB)"},
            "min_ram": {"type": "integer", "description": "Minimum RAM (MB)"},
            "container_format": {"type": "string", "description": "Container format"},
            "disk_format": {"type": "string", "description": "Disk format"},
            "size": {"type": "integer", "description": "Image size (bytes)"},
            "checksum": {"type": "string", "description": "Image checksum"},
            "created_at": {"type": "string", "description": "Creation timestamp"},
            "updated_at": {"type": "string", "description": "Last update timestamp"},
            "tags": {"type": "array", "description": "Image tags"},
        },
        "additionalProperties": {"type": "string"},
    }


@router.get("/v2/schemas/images")
async def get_images_schema() -> dict[str, Any]:
    """Get images collection schema."""
    return {
        "name": "images",
        "properties": {
            "images": {"type": "array", "items": {"$ref": "/v2/schemas/image"}},
            "first": {"type": "string"},
            "next": {"type": "string"},
            "schema": {"type": "string"},
        },
    }


@router.get("/v2/schemas/member")
async def get_member_schema() -> dict[str, Any]:
    """Get member schema."""
    return {
        "name": "member",
        "properties": {
            "image_id": {"type": "string", "description": "Image ID"},
            "member_id": {"type": "string", "description": "Member project ID"},
            "status": {"type": "string", "description": "Member status"},
            "created_at": {"type": "string", "description": "Creation timestamp"},
            "updated_at": {"type": "string", "description": "Last update timestamp"},
            "schema": {"type": "string"},
        },
    }


@router.get("/v2/schemas/members")
async def get_members_schema() -> dict[str, Any]:
    """Get members collection schema."""
    return {
        "name": "members",
        "properties": {
            "members": {"type": "array", "items": {"$ref": "/v2/schemas/member"}},
            "schema": {"type": "string"},
        },
    }
