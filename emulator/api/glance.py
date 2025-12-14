"""Glance Image API v2 endpoints for OpenStack emulator.

Implements the OpenStack Glance Image Service API v2.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db
from emulator.core.models import ContainerFormat, DiskFormat, ImageStatus, ImageVisibility, TaskStatus, TaskType
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


# Image Import/Export


class ImageImportRequest(BaseModel):
    """Image import request."""

    method: dict[str, Any]


class ImageImportBody(BaseModel):
    """Wrapper for image import request."""

    import_request: ImageImportRequest = Field(alias="import")


@router.post("/v2/images/{image_id}/import", status_code=202)
async def import_image(
    image_id: str,
    body: ImageImportBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Import image data using the specified method."""
    project_id = _get_project_id(x_auth_token)

    # Verify image exists and user has access
    image = db.get_glance_image(image_id, project_id=project_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Create an import task
    task = db.create_image_task(
        task_type=TaskType.IMPORT,
        input_data={"image_id": image_id, "import_method": body.import_request.method},
        owner=project_id,
    )

    # In a real implementation, this would trigger async import
    # For the emulator, we simulate immediate success
    image.status = ImageStatus.ACTIVE
    image.size = 1024 * 1024 * 100  # 100MB simulated

    return Response(status_code=202)


@router.get("/v2/images/{image_id}/tasks")
async def list_image_tasks(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List tasks for a specific image."""
    project_id = _get_project_id(x_auth_token)

    # Verify image exists and user has access
    image = db.get_glance_image(image_id, project_id=project_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    tasks = db.list_image_tasks(owner=project_id)
    # Filter for tasks related to this image
    image_tasks = [t for t in tasks if t.input.get("image_id") == image_id]

    return {"tasks": [task.to_dict() for task in image_tasks]}


# Image Tasks


class TaskCreateRequest(BaseModel):
    """Task creation request."""

    type: str  # import, export, clone
    input: dict[str, Any]


@router.get("/v2/tasks")
async def list_tasks(
    status: str | None = Query(None),
    type: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List image tasks."""
    project_id = _get_project_id(x_auth_token)

    # Convert string parameters to enums if provided
    status_enum = None
    type_enum = None
    if status:
        try:
            status_enum = TaskStatus(status)
        except ValueError:
            pass
    if type:
        try:
            type_enum = TaskType(type)
        except ValueError:
            pass

    tasks = db.list_image_tasks(owner=project_id, status=status_enum, type=type_enum)
    return {"tasks": [task.to_dict() for task in tasks]}


@router.post("/v2/tasks", status_code=201)
async def create_task(
    body: TaskCreateRequest,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an image task."""
    project_id = _get_project_id(x_auth_token)

    try:
        task_type = TaskType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {body.type}")

    task = db.create_image_task(
        task_type=task_type,
        input_data=body.input,
        owner=project_id,
    )

    return {"task": task.to_dict()}


@router.get("/v2/tasks/{task_id}")
async def get_task(
    task_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an image task by ID."""
    project_id = _get_project_id(x_auth_token)

    task = db.get_image_task(task_id, owner=project_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"task": task.to_dict()}


@router.delete("/v2/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an image task."""
    project_id = _get_project_id(x_auth_token)

    success = db.delete_image_task(task_id, owner=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")

    return Response(status_code=204)


# Metadata Definitions


class MetadefNamespaceRequest(BaseModel):
    """Metadef namespace request."""

    namespace: str
    display_name: str = ""
    description: str = ""
    visibility: str = "private"
    protected: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)


@router.get("/v2/metadefs/namespaces")
async def list_metadef_namespaces(
    visibility: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List metadata definition namespaces."""
    project_id = _get_project_id(x_auth_token)

    namespaces = db.list_metadef_namespaces(owner=project_id, visibility=visibility)
    return {"namespaces": [ns.to_dict() for ns in namespaces]}


@router.post("/v2/metadefs/namespaces", status_code=201)
async def create_metadef_namespace(
    body: MetadefNamespaceRequest,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a metadata definition namespace."""
    project_id = _get_project_id(x_auth_token)

    namespace = db.create_metadef_namespace(
        namespace=body.namespace,
        display_name=body.display_name,
        description=body.description,
        visibility=body.visibility,
        owner=project_id,
        properties=body.properties,
    )

    return namespace.to_dict()


@router.get("/v2/metadefs/namespaces/{namespace_name}")
async def get_metadef_namespace(
    namespace_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a metadata definition namespace."""
    project_id = _get_project_id(x_auth_token)

    namespace = db.get_metadef_namespace(namespace_name, owner=project_id)
    if not namespace:
        raise HTTPException(status_code=404, detail="Namespace not found")

    return namespace.to_dict()


@router.put("/v2/metadefs/namespaces/{namespace_name}")
async def update_metadef_namespace(
    namespace_name: str,
    body: MetadefNamespaceRequest,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a metadata definition namespace."""
    project_id = _get_project_id(x_auth_token)

    namespace = db.update_metadef_namespace(
        namespace=namespace_name,
        owner=project_id,
        display_name=body.display_name,
        description=body.description,
        visibility=body.visibility,
        protected=body.protected,
        properties=body.properties,
    )
    if not namespace:
        raise HTTPException(status_code=404, detail="Namespace not found")

    return namespace.to_dict()


@router.delete("/v2/metadefs/namespaces/{namespace_name}", status_code=204)
async def delete_metadef_namespace(
    namespace_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a metadata definition namespace."""
    project_id = _get_project_id(x_auth_token)

    success = db.delete_metadef_namespace(namespace_name, owner=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Namespace not found")

    return Response(status_code=204)


# Image Cache Management


@router.get("/v2/cache")
async def get_cache_status(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get image cache status."""
    _get_project_id(x_auth_token)  # Validate token (admin operation)

    return db.get_image_cache_status()


@router.delete("/v2/cache", status_code=204)
async def clear_cache(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Clear image cache."""
    _get_project_id(x_auth_token)  # Validate token (admin operation)

    db.clear_image_cache()
    return Response(status_code=204)


@router.put("/v2/cache/{image_id}", status_code=202)
async def cache_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Queue an image for caching."""
    project_id = _get_project_id(x_auth_token)

    # Verify image exists
    image = db.get_glance_image(image_id, project_id=project_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    db.cache_image(image_id, size=image.size or 0)
    return Response(status_code=202)


@router.delete("/v2/cache/{image_id}", status_code=204)
async def delete_cached_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Remove an image from cache."""
    _get_project_id(x_auth_token)  # Validate token (admin operation)

    success = db.delete_cached_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Image not found in cache")

    return Response(status_code=204)


# Discovery and Information


@router.get("/v2/info/stores")
async def get_stores_info(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get information about available stores."""
    _get_project_id(x_auth_token)  # Validate token

    stores = db.list_glance_stores()
    return {"stores": [store.to_dict() for store in stores]}


@router.get("/v2/info/import")
async def get_import_info(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get information about image import methods."""
    _get_project_id(x_auth_token)  # Validate token

    return {
        "import-methods": {
            "description": "Import methods available to the cloud operator.",
            "type": "array",
            "items": {
                "description": "An import method available to the cloud operator",
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "identifier to use when specifying this import method",
                    },
                    "description": {
                        "type": "string",
                        "description": "description of this import method",
                    },
                    "disabled": {
                        "type": "boolean",
                        "description": "whether this import method is currently disabled",
                    },
                },
            },
        },
        "import-methods-list": [
            {"name": "glance-direct", "description": "Direct upload to Glance", "disabled": False},
            {"name": "web-download", "description": "Download from web URL", "disabled": False},
        ],
    }


# Additional Schema Endpoints


@router.get("/v2/schemas/task")
async def get_task_schema() -> dict[str, Any]:
    """Get task schema."""
    return {
        "name": "task",
        "properties": {
            "id": {"type": "string", "description": "An identifier for the task"},
            "type": {
                "type": "string",
                "description": "The type of task represented by this content",
            },
            "status": {"type": "string", "description": "The current status of this task"},
            "owner": {"type": "string", "description": "The tenant ID of the task owner"},
            "created_at": {"type": "string", "description": "Date and time of task creation"},
            "updated_at": {
                "type": "string",
                "description": "Date and time of last task modification",
            },
            "expires_at": {"type": "string", "description": "Date and time of task expiration"},
            "input": {"type": "object", "description": "The parameters required by task"},
            "result": {"type": "object", "description": "The result of task execution"},
            "message": {"type": "string", "description": "Human-readable informational message"},
            "self": {"type": "string"},
            "schema": {"type": "string"},
        },
        "links": [
            {"rel": "self", "href": "/v2/schemas/task"},
            {"rel": "describedby", "href": "/v2/schemas/task"},
        ],
    }


@router.get("/v2/schemas/tasks")
async def get_tasks_schema() -> dict[str, Any]:
    """Get tasks collection schema."""
    return {
        "name": "tasks",
        "properties": {
            "tasks": {"type": "array", "items": {"$ref": "/v2/schemas/task"}},
            "first": {"type": "string"},
            "next": {"type": "string"},
            "schema": {"type": "string"},
        },
    }


@router.get("/v2/schemas/metadefs/namespace")
async def get_metadef_namespace_schema() -> dict[str, Any]:
    """Get metadef namespace schema."""
    return {
        "name": "namespace",
        "properties": {
            "namespace": {"type": "string", "description": "The unique namespace text"},
            "display_name": {"type": "string", "description": "The user-friendly name"},
            "description": {"type": "string", "description": "The description of the namespace"},
            "visibility": {"type": "string", "enum": ["public", "private"]},
            "protected": {
                "type": "boolean",
                "description": "Whether namespace is protected from deletion",
            },
            "owner": {"type": "string", "description": "The tenant ID of the namespace owner"},
            "properties": {"type": "object", "description": "Property definitions"},
            "objects": {"type": "array", "description": "Object definitions"},
            "resource_type_associations": {
                "type": "array",
                "description": "Resource type associations",
            },
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
            "self": {"type": "string"},
            "schema": {"type": "string"},
        },
    }
