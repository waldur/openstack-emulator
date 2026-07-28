"""Nova Compute API endpoints for OpenStack emulator."""

from typing import Any, TypeGuard

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from emulator.core.database import db
from emulator.core.exceptions import (
    FixedIPAlreadyInUseError,
    InvalidFixedIPError,
    PortInUseError,
)
from emulator.core.models import Server
from emulator.core.simple_auth import TokenInfo, validate_token_simple

router = APIRouter(tags=["compute"])


# Request/Response models
class ServerCreateNetwork(BaseModel):
    """Network configuration for server creation."""

    uuid: str | None = None
    port: str | None = None
    fixed_ip: str | None = None


class BlockDeviceMapping(BaseModel):
    """Block device mapping for server creation."""

    boot_index: int | None = None
    uuid: str | None = None
    source_type: str | None = None
    destination_type: str | None = None
    volume_size: int | None = None
    delete_on_termination: bool = True


class ServerCreateRequest(BaseModel):
    """Server creation request body."""

    name: str
    flavorRef: str
    imageRef: str | None = None
    key_name: str | None = None
    metadata: dict[str, str] | None = None
    security_groups: list[dict[str, str]] | None = None
    networks: list[ServerCreateNetwork] | None = None
    availability_zone: str | None = None
    block_device_mapping_v2: list[BlockDeviceMapping] | None = None
    user_data: str | None = None
    config_drive: bool | None = None
    min_count: int = 1
    max_count: int = 1


class ServerCreateBody(BaseModel):
    """Wrapper for server creation request."""

    server: ServerCreateRequest


class ServerUpdateRequest(BaseModel):
    """Server update request body."""

    name: str | None = None


class ServerUpdateBody(BaseModel):
    """Wrapper for server update request."""

    server: ServerUpdateRequest


class FlavorCreateRequest(BaseModel):
    """Flavor creation request body."""

    name: str
    vcpus: int
    ram: int
    disk: int
    id: str | None = None
    ephemeral: int = Field(default=0, alias="OS-FLV-EXT-DATA:ephemeral")
    swap: int = 0
    is_public: bool = Field(default=True, alias="os-flavor-access:is_public")
    description: str | None = None


class FlavorCreateBody(BaseModel):
    """Wrapper for flavor creation request."""

    flavor: FlavorCreateRequest


class KeypairCreateRequest(BaseModel):
    """Keypair creation request body."""

    name: str
    public_key: str | None = None
    type: str = "ssh"


class KeypairCreateBody(BaseModel):
    """Wrapper for keypair creation request."""

    keypair: KeypairCreateRequest


# Helper function to validate tokens
def get_token_or_raise(auth_token: str | None) -> TokenInfo:
    """Validate token using shared database."""
    return validate_token_simple(auth_token, "Nova")


def is_server_accessible(server: Server | None, token: TokenInfo) -> TypeGuard[Server]:
    if not server:
        return False
    return token.is_admin or server.tenant_id == token.project_id


# API Version endpoints
@router.get("/")
async def list_compute_versions() -> dict[str, Any]:
    """List all Compute API versions."""
    return {
        "versions": [
            {
                "id": "v2.0",
                "status": "SUPPORTED",
                "version": "",
                "min_version": "",
                "updated": "2011-01-21T11:33:21Z",
                "links": [{"rel": "self", "href": "/v2/"}],
            },
            {
                "id": "v2.1",
                "status": "CURRENT",
                "version": "2.87",
                "min_version": "2.1",
                "updated": "2013-07-23T11:33:21Z",
                "links": [{"rel": "self", "href": "/v2.1/"}],
            },
        ]
    }


@router.get("/v2.1")
@router.get("/v2.1/")
async def get_version_v21(request: Request) -> dict[str, Any]:
    """Get Compute API v2.1 details."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "version": {
            "id": "v2.1",
            "status": "CURRENT",
            "version": "2.87",
            "max_version": "2.87",
            "min_version": "2.1",
            "updated": "2013-07-23T11:33:21Z",
            "links": [{"rel": "self", "href": f"{base_url}/v2.1/"}],
            "media-types": [
                {
                    "base": "application/json",
                    "type": "application/vnd.openstack.compute+json;version=2.1",
                }
            ],
        }
    }


# Server endpoints
@router.get("/v2.1/servers")
async def list_servers(
    request: Request,
    status: str | None = None,
    name: str | None = None,
    flavor: str | None = None,
    image: str | None = None,
    limit: int | None = Query(None, ge=1),
    marker: str | None = None,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List servers (basic info)."""
    token = get_token_or_raise(x_auth_token)

    all_tenants = request.query_params.get("all_tenants")
    tenant_id = None if (token.is_admin and all_tenants) else token.project_id

    servers = db.list_servers(
        tenant_id=tenant_id,
        status=status,
        name=name,
        flavor=flavor,
        image=image,
        limit=limit,
        marker=marker,
    )

    return {
        "servers": [s.to_dict(detailed=False) for s in servers],
        "servers_links": [],
    }


@router.get("/v2.1/servers/detail")
async def list_servers_detail(
    request: Request,
    status: str | None = None,
    name: str | None = None,
    flavor: str | None = None,
    image: str | None = None,
    limit: int | None = Query(None, ge=1),
    marker: str | None = None,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List servers (detailed info)."""
    token = get_token_or_raise(x_auth_token)

    all_tenants = request.query_params.get("all_tenants")
    tenant_id = None if (token.is_admin and all_tenants) else token.project_id

    servers = db.list_servers(
        tenant_id=tenant_id,
        status=status,
        name=name,
        flavor=flavor,
        image=image,
        limit=limit,
        marker=marker,
    )

    return {
        "servers": [s.to_dict(detailed=True) for s in servers],
        "servers_links": [],
    }


@router.post("/v2.1/servers", status_code=202)
async def create_server(
    body: ServerCreateBody,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new server."""
    token = get_token_or_raise(x_auth_token)
    req = body.server

    # Validate flavor exists
    flavor = db.get_flavor(req.flavorRef)
    if not flavor:
        raise HTTPException(status_code=400, detail=f"Flavor {req.flavorRef} not found")

    # Validate image exists (if provided)
    if req.imageRef:
        image = db.get_image(req.imageRef)
        if not image:
            raise HTTPException(status_code=400, detail=f"Image {req.imageRef} not found")

    # Convert networks to dict format
    networks = None
    if req.networks:
        networks = [{"uuid": n.uuid, "port": n.port, "fixed_ip": n.fixed_ip} for n in req.networks]

    server = db.create_server(
        name=req.name,
        flavor_id=req.flavorRef,
        image_id=req.imageRef or "",
        tenant_id=token.project_id,
        user_id=token.user_id,
        key_name=req.key_name,
        metadata=req.metadata,
        security_groups=req.security_groups,
        availability_zone=req.availability_zone or "nova",
        networks=networks,
        config_drive=req.config_drive,
    )

    # Return response with admin password
    response_data = server.to_dict(detailed=False)
    response_data["adminPass"] = server.admin_pass
    response_data["security_groups"] = server.security_groups

    return {"server": response_data}


@router.get("/v2.1/servers/{server_id}")
async def get_server(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a server by ID."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    return {"server": server.to_dict(detailed=True)}


@router.put("/v2.1/servers/{server_id}")
async def update_server(
    server_id: str,
    body: ServerUpdateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a server."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    updated = db.update_server(server_id, name=body.server.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Server not found")

    return {"server": updated.to_dict(detailed=True)}


@router.delete("/v2.1/servers/{server_id}", status_code=204)
async def delete_server(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a server."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    if not db.delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")

    return Response(status_code=204)


# Server actions
@router.post("/v2.1/servers/{server_id}/action", status_code=202, response_model=None)
async def server_action(
    server_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response | dict[str, Any]:
    """Perform an action on a server."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    body = await request.json()

    # Handle different actions
    if "os-start" in body:
        if not db.server_action(server_id, "start"):
            raise HTTPException(status_code=409, detail="Cannot start server in current state")
        return Response(status_code=202)

    elif "os-stop" in body:
        if not db.server_action(server_id, "stop"):
            raise HTTPException(status_code=409, detail="Cannot stop server in current state")
        return Response(status_code=202)

    elif "reboot" in body:
        body["reboot"].get("type", "SOFT")
        if not db.server_action(server_id, "reboot"):
            raise HTTPException(status_code=409, detail="Cannot reboot server in current state")
        return Response(status_code=202)

    elif "pause" in body:
        if not db.server_action(server_id, "pause"):
            raise HTTPException(status_code=409, detail="Cannot pause server in current state")
        return Response(status_code=202)

    elif "unpause" in body:
        if not db.server_action(server_id, "unpause"):
            raise HTTPException(status_code=409, detail="Cannot unpause server in current state")
        return Response(status_code=202)

    elif "suspend" in body:
        if not db.server_action(server_id, "suspend"):
            raise HTTPException(status_code=409, detail="Cannot suspend server in current state")
        return Response(status_code=202)

    elif "resume" in body:
        if not db.server_action(server_id, "resume"):
            raise HTTPException(status_code=409, detail="Cannot resume server in current state")
        return Response(status_code=202)

    elif "shelve" in body:
        if not db.server_action(server_id, "shelve"):
            raise HTTPException(status_code=409, detail="Cannot shelve server in current state")
        return Response(status_code=202)

    elif "unshelve" in body:
        if not db.server_action(server_id, "unshelve"):
            raise HTTPException(status_code=409, detail="Cannot unshelve server in current state")
        return Response(status_code=202)

    elif "os-getConsoleOutput" in body:
        # Return fake console output
        return {"output": "Console output not available in emulator\n"}

    elif "os-getVNCConsole" in body or "os-getSPICEConsole" in body:
        # Return fake console URL
        return {
            "console": {
                "type": "novnc",
                "url": "http://localhost:6080/vnc_auto.html?token=fake-token",
            }
        }

    elif "addSecurityGroup" in body:
        sg_data = body["addSecurityGroup"]
        sg_name = sg_data.get("name")
        if not sg_name:
            raise HTTPException(status_code=400, detail="Security group name required")
        # Add security group to server
        if not any(sg["name"] == sg_name for sg in server.security_groups):
            server.security_groups.append({"name": sg_name})
        return Response(status_code=202)

    elif "removeSecurityGroup" in body:
        sg_data = body["removeSecurityGroup"]
        sg_name = sg_data.get("name")
        if not sg_name:
            raise HTTPException(status_code=400, detail="Security group name required")
        # Remove security group from server
        original_len = len(server.security_groups)
        server.security_groups = [sg for sg in server.security_groups if sg["name"] != sg_name]
        if len(server.security_groups) == original_len:
            raise HTTPException(
                status_code=404, detail=f"Security group {sg_name} not found on server"
            )
        return Response(status_code=202)

    elif "resize" in body:
        resize_data = body["resize"]
        flavor_ref = resize_data.get("flavorRef")
        if not flavor_ref:
            raise HTTPException(status_code=400, detail="flavorRef is required for resize")
        # Validate flavor exists
        flavor = db.get_flavor(flavor_ref)
        if not flavor:
            raise HTTPException(status_code=400, detail=f"Flavor {flavor_ref} not found")
        if not db.server_resize(server_id, flavor_ref):
            raise HTTPException(status_code=409, detail="Cannot resize server in current state")
        return Response(status_code=202)

    elif "confirmResize" in body:
        if not db.server_action(server_id, "confirmResize"):
            raise HTTPException(status_code=409, detail="Cannot confirm resize in current state")
        return Response(status_code=204)

    elif "revertResize" in body:
        if not db.server_action(server_id, "revertResize"):
            raise HTTPException(status_code=409, detail="Cannot revert resize in current state")
        return Response(status_code=202)

    elif "createImage" in body:
        create_image_data = body["createImage"]
        image_name = create_image_data.get("name")
        if not image_name:
            raise HTTPException(status_code=400, detail="Image name is required")
        metadata = create_image_data.get("metadata", {})
        image = db.create_server_snapshot(server_id, image_name, metadata)
        if not image:
            raise HTTPException(status_code=404, detail="Server not found")
        # Return the image ID in the Location header (OpenStack convention)
        return Response(
            status_code=202,
            headers={"Location": f"/v2/images/{image.id}"},
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {list(body.keys())}")


# Security Groups Support
@router.get("/v2.1/servers/{server_id}/os-security-groups")
async def list_server_security_groups(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List security groups for a server."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    # Ensure default security group exists for this tenant
    project_id = server.tenant_id if token.is_admin else token.project_id
    db.get_or_create_default_security_group(project_id)

    # Get full security group details
    # Server only stores names: [{"name": "default"}]
    result_sgs = []
    for server_sg in server.security_groups:
        sg_name = server_sg.get("name")
        if sg_name:
            # Find the security group by name in the project
            # Note: list_security_groups returns a list
            sgs = db.list_security_groups(project_id=project_id, name=sg_name)
            if sgs:
                # Use the first match (names should be unique per project)
                # Create a shallow copy to ensure we don't mutate any shared state
                sg_dict = sgs[0].to_dict().copy()
                # Rename security_group_rules to rules for this specific endpoint
                if "security_group_rules" in sg_dict:
                    sg_dict["rules"] = sg_dict.pop("security_group_rules")
                result_sgs.append(sg_dict)

    return {"security_groups": result_sgs}


# Server metadata
@router.get("/v2.1/servers/{server_id}/metadata")
async def get_server_metadata(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get server metadata."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    return {"metadata": server.metadata}


@router.put("/v2.1/servers/{server_id}/metadata")
async def update_server_metadata(
    server_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update server metadata."""
    token = get_token_or_raise(x_auth_token)

    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    body = await request.json()
    metadata = body.get("metadata", {})

    updated = db.update_server(server_id, metadata=metadata)
    return {"metadata": updated.metadata if updated else {}}


def _parse_is_public(value: str | None) -> bool | None:
    """Parse is_public query parameter.

    OpenStack SDK sends 'None' as a string, so we need to handle that case.
    """
    if value is None or value == "None":
        return None
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    return None


# Flavor endpoints
@router.get("/v2.1/flavors")
async def list_flavors(
    is_public: str | None = Query(None),
    limit: int | None = Query(None, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List flavors (basic info)."""
    get_token_or_raise(x_auth_token)

    flavors = db.list_flavors(is_public=_parse_is_public(is_public), limit=limit)
    return {
        "flavors": [f.to_dict(detailed=False) for f in flavors],
        "flavors_links": [],
    }


@router.get("/v2.1/flavors/detail")
async def list_flavors_detail(
    is_public: str | None = Query(None),
    limit: int | None = Query(None, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List flavors (detailed info)."""
    get_token_or_raise(x_auth_token)

    flavors = db.list_flavors(is_public=_parse_is_public(is_public), limit=limit)
    return {
        "flavors": [f.to_dict(detailed=True) for f in flavors],
        "flavors_links": [],
    }


@router.get("/v2.1/flavors/{flavor_id}")
async def get_flavor(
    flavor_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a flavor by ID."""
    get_token_or_raise(x_auth_token)

    flavor = db.get_flavor(flavor_id)
    if not flavor:
        raise HTTPException(status_code=404, detail="Flavor not found")

    return {"flavor": flavor.to_dict(detailed=True)}


@router.post("/v2.1/flavors", status_code=200)
async def create_flavor(
    body: FlavorCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new flavor."""
    get_token_or_raise(x_auth_token)

    req = body.flavor
    flavor = db.create_flavor(
        name=req.name,
        vcpus=req.vcpus,
        ram=req.ram,
        disk=req.disk,
        flavor_id=req.id,
        ephemeral=req.ephemeral,
        swap=req.swap,
        is_public=req.is_public,
        description=req.description or "",
    )

    return {"flavor": flavor.to_dict(detailed=True)}


@router.delete("/v2.1/flavors/{flavor_id}", status_code=202)
async def delete_flavor(
    flavor_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a flavor."""
    get_token_or_raise(x_auth_token)

    if not db.delete_flavor(flavor_id):
        raise HTTPException(status_code=404, detail="Flavor not found")

    return Response(status_code=202)


# Image endpoints (Nova-style, deprecated but still used)
@router.get("/v2.1/images")
async def list_images(
    status: str | None = None,
    name: str | None = None,
    limit: int | None = Query(None, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List images (basic info)."""
    get_token_or_raise(x_auth_token)

    images = db.list_images(status=status, name=name, limit=limit)
    return {
        "images": [i.to_dict(detailed=False) for i in images],
        "images_links": [],
    }


@router.get("/v2.1/images/detail")
async def list_images_detail(
    status: str | None = None,
    name: str | None = None,
    limit: int | None = Query(None, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List images (detailed info)."""
    get_token_or_raise(x_auth_token)

    images = db.list_images(status=status, name=name, limit=limit)
    return {
        "images": [i.to_dict(detailed=True) for i in images],
        "images_links": [],
    }


@router.get("/v2.1/images/{image_id}")
async def get_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an image by ID."""
    get_token_or_raise(x_auth_token)

    image = db.get_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return {"image": image.to_dict(detailed=True)}


@router.delete("/v2.1/images/{image_id}", status_code=204)
async def delete_image(
    image_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an image."""
    get_token_or_raise(x_auth_token)

    if not db.delete_image(image_id):
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(status_code=204)


# Keypair endpoints
@router.get("/v2.1/os-keypairs")
async def list_keypairs(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    user_id: str | None = Query(None),
    fingerprint: str | None = Query(None, alias="fingerprint"),
) -> dict[str, Any]:
    """List keypairs with optional filtering by user_id and fingerprint."""
    token = get_token_or_raise(x_auth_token)

    # Use provided user_id or default to token's user
    effective_user_id = user_id or token.user_id
    keypairs = db.list_keypairs(user_id=effective_user_id)

    # Filter by fingerprint if provided
    if fingerprint:
        keypairs = [kp for kp in keypairs if kp.fingerprint == fingerprint]

    return {"keypairs": [{"keypair": kp.to_dict()} for kp in keypairs]}


@router.post("/v2.1/os-keypairs", status_code=200)
async def create_keypair(
    body: KeypairCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new keypair."""
    token = get_token_or_raise(x_auth_token)

    req = body.keypair
    keypair = db.create_keypair(
        name=req.name,
        user_id=token.user_id,
        public_key=req.public_key,
        key_type=req.type,
    )

    response = {"keypair": keypair.to_dict()}
    # If no public key was provided, we "generated" one
    if not req.public_key:
        response["keypair"]["private_key"] = (
            "-----BEGIN RSA PRIVATE KEY-----\n...(emulated)...\n-----END RSA PRIVATE KEY-----"
        )

    return response


@router.get("/v2.1/os-keypairs/{keypair_name}")
async def get_keypair(
    keypair_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a keypair by name."""
    token = get_token_or_raise(x_auth_token)

    keypair = db.get_keypair(name=keypair_name, user_id=token.user_id)
    if not keypair:
        raise HTTPException(status_code=404, detail="Keypair not found")

    return {"keypair": keypair.to_dict()}


@router.delete("/v2.1/os-keypairs/{keypair_name}", status_code=202)
async def delete_keypair(
    keypair_name: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a keypair."""
    token = get_token_or_raise(x_auth_token)

    if not db.delete_keypair(name=keypair_name, user_id=token.user_id):
        raise HTTPException(status_code=404, detail="Keypair not found")

    return Response(status_code=202)


# Limits endpoint
@router.get("/v2.1/limits")
async def get_limits(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get compute limits for the current project."""
    token = get_token_or_raise(x_auth_token)

    # Count current resources
    servers = db.list_servers(tenant_id=token.project_id)
    server_count = len(servers)
    total_ram = 0
    total_cores = 0
    for s in servers:
        flavor = db.get_flavor(s.flavor_id)
        if flavor:
            total_ram += flavor.ram
            total_cores += flavor.vcpus

    return {
        "limits": {
            "rate": [],
            "absolute": {
                "maxServerMeta": 128,
                "maxPersonality": 5,
                "maxPersonalitySize": 10240,
                "maxTotalRAMSize": 51200,
                "maxTotalInstances": 10,
                "maxTotalCores": 20,
                "maxTotalKeypairs": 100,
                "maxSecurityGroups": 10,
                "maxSecurityGroupRules": 20,
                "maxTotalFloatingIps": 10,
                "maxServerGroups": 10,
                "maxServerGroupMembers": 10,
                "totalRAMUsed": total_ram,
                "totalCoresUsed": total_cores,
                "totalInstancesUsed": server_count,
                "totalFloatingIpsUsed": 0,
                "totalSecurityGroupsUsed": 1,
                "totalServerGroupsUsed": 0,
            },
        }
    }


# Availability zones
@router.get("/v2.1/os-availability-zone")
async def list_availability_zones(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List availability zones."""
    get_token_or_raise(x_auth_token)

    return {
        "availabilityZoneInfo": [
            {
                "zoneName": "nova",
                "zoneState": {"available": True},
                "hosts": None,
            }
        ]
    }


@router.get("/v2.1/os-availability-zone/detail")
async def list_availability_zones_detail(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List availability zones with details."""
    get_token_or_raise(x_auth_token)

    return {
        "availabilityZoneInfo": [
            {
                "zoneName": "nova",
                "zoneState": {"available": True},
                "hosts": {
                    "compute-host-1": {
                        "nova-compute": {
                            "active": True,
                            "available": True,
                            "updated_at": "2024-01-01T00:00:00.000000",
                        }
                    }
                },
            }
        ]
    }


# Hypervisors (simplified)
@router.get("/v2.1/os-hypervisors")
async def list_hypervisors(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List hypervisors."""
    get_token_or_raise(x_auth_token)

    return {
        "hypervisors": [
            {
                "id": "1",
                "hypervisor_hostname": "compute-host-1",
                "state": "up",
                "status": "enabled",
            }
        ]
    }


@router.get("/v2.1/os-hypervisors/detail")
async def list_hypervisors_detail(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List hypervisors with details."""
    get_token_or_raise(x_auth_token)

    stats = db.get_hypervisor_statistics()

    return {
        "hypervisors": [
            {
                "id": "1",
                "hypervisor_hostname": "compute-host-1",
                "state": "up",
                "status": "enabled",
                "host_ip": "10.0.0.1",
                "hypervisor_type": "QEMU",
                "hypervisor_version": 6002000,
                "cpu_info": '{"vendor": "Intel", "model": "IvyBridge", "arch": "x86_64", "features": ["ssse3", "sse4.1", "sse4.2"], "topology": {"cores": 8, "threads": 2, "sockets": 2}}',
                "vcpus": stats["vcpus"],
                "vcpus_used": stats["vcpus_used"],
                "memory_mb": stats["memory_mb"],
                "memory_mb_used": stats["memory_mb_used"],
                "local_gb": stats["local_gb"],
                "local_gb_used": stats["local_gb_used"],
                "free_ram_mb": stats["free_ram_mb"],
                "free_disk_gb": stats["free_disk_gb"],
                "current_workload": stats["current_workload"],
                "running_vms": stats["running_vms"],
                "disk_available_least": stats["disk_available_least"],
                "service": {
                    "id": 1,
                    "host": "compute-host-1",
                    "disabled_reason": None,
                },
            }
        ]
    }


@router.get("/v2.1/os-hypervisors/statistics")
async def get_hypervisor_statistics(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get hypervisor statistics."""
    get_token_or_raise(x_auth_token)

    # Get dynamic statistics from database
    stats = db.get_hypervisor_statistics()
    return {"hypervisor_statistics": stats}


# ==================== Server Groups ====================


class ServerGroupCreateRequest(BaseModel):
    """Server group creation request body."""

    name: str
    policies: list[str] = []


class ServerGroupCreateBody(BaseModel):
    """Wrapper for server group creation request."""

    server_group: ServerGroupCreateRequest


@router.get("/v2.1/os-server-groups")
async def list_server_groups(
    all_projects: bool = Query(False),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List server groups."""
    token = get_token_or_raise(x_auth_token)

    groups = db.list_server_groups(
        project_id=token.project_id,
        all_projects=all_projects,
    )

    return {"server_groups": [g.to_dict() for g in groups]}


@router.post("/v2.1/os-server-groups", status_code=200)
async def create_server_group(
    body: ServerGroupCreateBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a new server group."""
    token = get_token_or_raise(x_auth_token)

    req = body.server_group
    group = db.create_server_group(
        name=req.name,
        policies=req.policies,
        project_id=token.project_id,
        user_id=token.user_id,
    )

    return {"server_group": group.to_dict()}


@router.get("/v2.1/os-server-groups/{server_group_id}")
async def get_server_group(
    server_group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a server group by ID."""
    token = get_token_or_raise(x_auth_token)

    group = db.get_server_group(server_group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Server group not found")

    if group.project_id != token.project_id:
        raise HTTPException(status_code=404, detail="Server group not found")

    return {"server_group": group.to_dict()}


@router.delete("/v2.1/os-server-groups/{server_group_id}", status_code=204)
async def delete_server_group(
    server_group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a server group."""
    token = get_token_or_raise(x_auth_token)

    group = db.get_server_group(server_group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Server group not found")

    if group.project_id != token.project_id:
        raise HTTPException(status_code=404, detail="Server group not found")

    if not db.delete_server_group(server_group_id):
        raise HTTPException(status_code=404, detail="Server group not found")

    return Response(status_code=204)


# ==================== Quotas ====================


@router.get("/v2.1/os-quota-sets/{tenant_id}")
async def get_quota_set(
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get compute quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    quota = db.get_nova_quota(tenant_id)
    return {"quota_set": quota.to_dict()}


@router.get("/v2.1/os-quota-sets/{tenant_id}/detail")
async def get_quota_set_detail(
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get detailed compute quota set with usage for a tenant."""
    get_token_or_raise(x_auth_token)

    quota = db.get_nova_quota(tenant_id)
    usage = db.get_nova_quota_usage(tenant_id)

    detail = {
        "id": tenant_id,
        "instances": {
            "limit": quota.instances,
            "in_use": usage.get("instances", 0),
            "reserved": 0,
        },
        "cores": {"limit": quota.cores, "in_use": usage.get("cores", 0), "reserved": 0},
        "ram": {"limit": quota.ram, "in_use": usage.get("ram", 0), "reserved": 0},
        "metadata_items": {"limit": quota.metadata_items, "in_use": 0, "reserved": 0},
        "injected_files": {"limit": quota.injected_files, "in_use": 0, "reserved": 0},
        "injected_file_content_bytes": {
            "limit": quota.injected_file_content_bytes,
            "in_use": 0,
            "reserved": 0,
        },
        "injected_file_path_bytes": {
            "limit": quota.injected_file_path_bytes,
            "in_use": 0,
            "reserved": 0,
        },
        "key_pairs": {
            "limit": quota.key_pairs,
            "in_use": usage.get("key_pairs", 0),
            "reserved": 0,
        },
        "server_groups": {
            "limit": quota.server_groups,
            "in_use": usage.get("server_groups", 0),
            "reserved": 0,
        },
        "server_group_members": {
            "limit": quota.server_group_members,
            "in_use": 0,
            "reserved": 0,
        },
    }

    return {"quota_set": detail}


@router.put("/v2.1/os-quota-sets/{tenant_id}")
async def update_quota_set(
    tenant_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update compute quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    body = await request.json()
    quota_data = body.get("quota_set", {})

    quota = db.update_nova_quota(
        project_id=tenant_id,
        instances=quota_data.get("instances"),
        cores=quota_data.get("cores"),
        ram=quota_data.get("ram"),
        metadata_items=quota_data.get("metadata_items"),
        injected_files=quota_data.get("injected_files"),
        injected_file_content_bytes=quota_data.get("injected_file_content_bytes"),
        injected_file_path_bytes=quota_data.get("injected_file_path_bytes"),
        key_pairs=quota_data.get("key_pairs"),
        server_groups=quota_data.get("server_groups"),
        server_group_members=quota_data.get("server_group_members"),
    )

    return {"quota_set": quota.to_dict()}


@router.delete("/v2.1/os-quota-sets/{tenant_id}", status_code=202)
async def delete_quota_set(
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete (reset) compute quota set for a tenant."""
    get_token_or_raise(x_auth_token)

    db.delete_nova_quota(tenant_id)
    return Response(status_code=202)


@router.get("/v2.1/os-quota-sets/{tenant_id}/defaults")
async def get_quota_set_defaults(
    tenant_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get default compute quota set."""
    get_token_or_raise(x_auth_token)

    # Return default quota values
    from emulator.core.models import NovaQuota

    default_quota = NovaQuota(project_id=tenant_id)
    return {"quota_set": default_quota.to_dict()}


# Extensions endpoints


@router.get("/v2.1/extensions")
async def list_extensions(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List all available Nova extensions."""
    get_token_or_raise(x_auth_token)

    extensions = db.list_nova_extensions()
    return {"extensions": [ext.to_dict() for ext in extensions]}


@router.get("/v2.1/extensions/{extension_alias}")
async def get_extension(
    extension_alias: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get details for a specific extension."""
    get_token_or_raise(x_auth_token)

    extension = db.get_nova_extension(extension_alias)
    if not extension:
        raise HTTPException(status_code=404, detail=f"Extension {extension_alias} not found")

    return {"extension": extension.to_dict()}


# Server Volume Attachments


class VolumeAttachmentRequest(BaseModel):
    """Volume attachment request."""

    volumeId: str
    device: str | None = None
    tag: str | None = None
    delete_on_termination: bool = False


class VolumeAttachmentBody(BaseModel):
    """Wrapper for volume attachment request."""

    volumeAttachment: VolumeAttachmentRequest


@router.get("/v2.1/servers/{server_id}/os-volume_attachments")
async def list_server_volume_attachments(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List volume attachments for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    attachments = db.list_server_volume_attachments(server_id)
    return {"volumeAttachments": [attachment.to_dict() for attachment in attachments]}


@router.post("/v2.1/servers/{server_id}/os-volume_attachments", status_code=200)
async def attach_volume_to_server(
    server_id: str,
    body: VolumeAttachmentBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Attach a volume to a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    # Verify volume exists
    volume = db.get_volume(body.volumeAttachment.volumeId, project_id=token.project_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    attachment = db.attach_volume_to_server(
        server_id=server_id,
        volume_id=body.volumeAttachment.volumeId,
        device=body.volumeAttachment.device,
        tag=body.volumeAttachment.tag,
        delete_on_termination=body.volumeAttachment.delete_on_termination,
    )
    success = db.attach_volume(
        volume_id=body.volumeAttachment.volumeId,
        server_id=server_id,
        device=body.volumeAttachment.device or "/dev/vdb",
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to attach volume")

    return {"volumeAttachment": attachment.to_dict()}


@router.get("/v2.1/servers/{server_id}/os-volume_attachments/{attachment_id}")
async def get_server_volume_attachment(
    server_id: str,
    attachment_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a specific volume attachment."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    attachment = db.get_server_volume_attachment(server_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Volume attachment not found")

    return {"volumeAttachment": attachment.to_dict()}


@router.delete("/v2.1/servers/{server_id}/os-volume_attachments/{attachment_id}", status_code=202)
async def detach_volume_from_server(
    server_id: str,
    attachment_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Detach a volume from a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    success = db.detach_volume_from_server(server_id, attachment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Volume attachment not found")

    attachment = db.get_server_volume_attachment(server_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Volume attachment not found")

    success = db.detach_volume(
        volume_id=attachment.volume_id,
        attachment_id=attachment_id,
        project_id=token.project_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Volume attachment not found")

    return Response(status_code=202)


# Server Network Interfaces


class InterfaceAttachmentRequest(BaseModel):
    """Interface attachment request."""

    net_id: str | None = None
    port_id: str | None = None
    fixed_ip: str | None = None


class InterfaceAttachmentBody(BaseModel):
    """Wrapper for interface attachment request."""

    interfaceAttachment: InterfaceAttachmentRequest


@router.get("/v2.1/servers/{server_id}/os-interface")
async def list_server_interfaces(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List network interfaces for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    interfaces = db.list_server_network_interfaces(server_id)
    return {"interfaceAttachments": [interface.to_dict() for interface in interfaces]}


@router.post("/v2.1/servers/{server_id}/os-interface", status_code=200)
async def attach_interface_to_server(
    server_id: str,
    body: InterfaceAttachmentBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Attach a network interface to a server.

    Mirrors Nova's os-interface contract: request-shape validation first,
    then port/network resolution in the caller's project scope. A port owned
    by another project is invisible to a non-admin token and yields the same
    404 as a nonexistent port, exactly like Nova asking Neutron with the
    user's context.
    """
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    attachment = body.interfaceAttachment
    if attachment.net_id and attachment.port_id:
        raise HTTPException(status_code=400, detail="Must not input both network_id and port_id")
    if attachment.fixed_ip and not attachment.net_id:
        raise HTTPException(status_code=400, detail="Must input network_id when request IP address")

    # Admin tokens see resources across projects; tenant tokens only their own.
    project_filter = None if token.is_admin else token.project_id

    nova_created = False
    if attachment.port_id:
        port = db.get_port(attachment.port_id, project_id=project_filter)
        if port is None:
            raise HTTPException(
                status_code=404,
                detail=f"Port id {attachment.port_id} could not be found.",
            )
    else:
        if not attachment.net_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "More than one possible network found. Specify network "
                    "ID(s) to select which one(s) to connect to."
                ),
            )
        network = db.get_network(attachment.net_id, project_id=project_filter)
        if network is None:
            raise HTTPException(
                status_code=404,
                detail=f"Network {attachment.net_id} could not be found.",
            )
        fixed_ips = None
        if attachment.fixed_ip:
            # subnet_id is resolved from the CIDR by create_port validation.
            fixed_ips = [{"ip_address": attachment.fixed_ip}]
        # Nova creates the port on behalf of the instance's project.
        try:
            port = db.create_port(
                network_id=attachment.net_id,
                project_id=server.tenant_id,
                fixed_ips=fixed_ips,
                validate_fixed_ips=True,
            )
        except InvalidFixedIPError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Fixed IP {exc.ip} is not a valid ip address for network {exc.network_id}."
                ),
            ) from exc
        except FixedIPAlreadyInUseError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Fixed IP {exc.ip} is already in use.",
            ) from exc
        if port is None:
            raise HTTPException(
                status_code=404,
                detail=f"Network {attachment.net_id} could not be found.",
            )
        nova_created = True

    try:
        interface = db.attach_interface_to_server(
            server_id=server_id, port=port, nova_created=nova_created
        )
    except PortInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Port {exc.port_id} is still in use.",
        ) from exc

    return {"interfaceAttachment": interface.to_dict()}


@router.get("/v2.1/servers/{server_id}/os-interface/{port_id}")
async def get_server_interface(
    server_id: str,
    port_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a specific network interface."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    interface = db.get_server_network_interface(server_id, port_id)
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")

    return {"interfaceAttachment": interface.to_dict()}


@router.delete("/v2.1/servers/{server_id}/os-interface/{port_id}", status_code=202)
async def detach_interface_from_server(
    server_id: str,
    port_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Detach a network interface from a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    success = db.detach_interface_from_server(server_id, port_id)
    if not success:
        raise HTTPException(status_code=404, detail="Interface not found")

    return Response(status_code=202)


# Server Diagnostics


@router.get("/v2.1/servers/{server_id}/diagnostics")
async def get_server_diagnostics(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get diagnostics for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        diagnostics = db.get_server_diagnostics(server_id)
        return diagnostics.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Server Console Support


class ConsoleRequest(BaseModel):
    """Console creation request."""

    type: str = "novnc"  # novnc, spice, serial


class ConsoleBody(BaseModel):
    """Wrapper for console request."""

    console: ConsoleRequest


class RemoteConsoleRequest(BaseModel):
    """Remote console creation request."""

    type: str = "novnc"  # novnc, spice-html5, serial
    protocol: str = "vnc"  # vnc, spice


class RemoteConsoleBody(BaseModel):
    """Wrapper for remote console request."""

    remote_console: RemoteConsoleRequest


@router.get("/v2.1/servers/{server_id}/consoles")
async def list_server_consoles(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List consoles for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    consoles = db.list_server_consoles(server_id)
    return {"consoles": [console.to_dict() for console in consoles]}


@router.post("/v2.1/servers/{server_id}/consoles", status_code=200)
async def create_server_console(
    server_id: str,
    body: ConsoleBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a console for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    console = db.create_server_console(server_id, body.console.type)
    return {"console": console.to_dict()}


@router.get("/v2.1/servers/{server_id}/consoles/{console_id}")
async def get_server_console(
    server_id: str,
    console_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a specific console."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    console = db.get_server_console(server_id, console_id)
    if not console:
        raise HTTPException(status_code=404, detail="Console not found")

    return {"console": console.to_dict()}


@router.delete("/v2.1/servers/{server_id}/consoles/{console_id}", status_code=202)
async def delete_server_console(
    server_id: str,
    console_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a server console."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    success = db.delete_server_console(server_id, console_id)
    if not success:
        raise HTTPException(status_code=404, detail="Console not found")

    return Response(status_code=202)


@router.post("/v2.1/servers/{server_id}/remote-consoles", status_code=200)
async def create_remote_console(
    server_id: str,
    body: RemoteConsoleBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a remote console for server access."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    console = db.create_remote_console(
        server_id, body.remote_console.type, body.remote_console.protocol
    )
    return {"remote_console": console.to_dict()}


# Server Tags


class ServerTagsBody(BaseModel):
    """Server tags update request."""

    tags: list[str]


@router.get("/v2.1/servers/{server_id}/tags")
async def list_server_tags(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List tags for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    tags = db.list_server_tags(server_id)
    return {"tags": tags}


@router.put("/v2.1/servers/{server_id}/tags", status_code=200)
async def replace_server_tags(
    server_id: str,
    body: ServerTagsBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Replace all tags for a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    db.replace_server_tags(server_id, body.tags)
    return {"tags": body.tags}


@router.delete("/v2.1/servers/{server_id}/tags", status_code=204)
async def clear_server_tags(
    server_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Clear all tags from a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    db.clear_server_tags(server_id)
    return Response(status_code=204)


@router.get("/v2.1/servers/{server_id}/tags/{tag}")
async def check_server_tag(
    server_id: str,
    tag: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Check if a server has a specific tag."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    tags = db.list_server_tags(server_id)
    if tag not in tags:
        raise HTTPException(status_code=404, detail="Tag not found")

    return Response(status_code=204)


@router.put("/v2.1/servers/{server_id}/tags/{tag}", status_code=201)
async def add_server_tag(
    server_id: str,
    tag: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Add a tag to a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    # Check if tag already exists
    tags = db.list_server_tags(server_id)
    status_code = 200 if tag in tags else 201

    db.add_server_tag(server_id, tag)
    return Response(status_code=status_code)


@router.delete("/v2.1/servers/{server_id}/tags/{tag}", status_code=204)
async def remove_server_tag(
    server_id: str,
    tag: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Remove a tag from a server."""
    token = get_token_or_raise(x_auth_token)

    # Verify server exists and user has access
    server = db.get_server(server_id)
    if not is_server_accessible(server, token):
        raise HTTPException(status_code=404, detail="Server not found")

    success = db.remove_server_tag(server_id, tag)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")

    return Response(status_code=204)
