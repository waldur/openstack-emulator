"""Octavia Load Balancer API routes for OpenStack emulator."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db

router = APIRouter(tags=["octavia"])


# Pydantic models for request/response validation


class LoadBalancerCreateRequest(BaseModel):
    """Request model for creating a load balancer."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    vip_subnet_id: str | None = Field(default=None, alias="vip_subnet_id")
    vip_network_id: str | None = Field(default=None, alias="vip_network_id")
    vip_address: str | None = Field(default=None, alias="vip_address")
    flavor_id: str | None = Field(default=None, alias="flavor_id")
    provider: str = "amphora"
    availability_zone: str | None = Field(default=None, alias="availability_zone")
    tags: list[str] | None = None


class LoadBalancerCreateBody(BaseModel):
    """Request body for creating a load balancer."""

    loadbalancer: LoadBalancerCreateRequest


class LoadBalancerUpdateRequest(BaseModel):
    """Request model for updating a load balancer."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    tags: list[str] | None = None


class LoadBalancerUpdateBody(BaseModel):
    """Request body for updating a load balancer."""

    loadbalancer: LoadBalancerUpdateRequest


class ListenerCreateRequest(BaseModel):
    """Request model for creating a listener."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    protocol: str
    protocol_port: int = Field(alias="protocol_port")
    loadbalancer_id: str = Field(alias="loadbalancer_id")
    connection_limit: int = Field(default=-1, alias="connection_limit")
    default_pool_id: str | None = Field(default=None, alias="default_pool_id")
    default_tls_container_ref: str | None = Field(
        default=None, alias="default_tls_container_ref"
    )
    sni_container_refs: list[str] | None = Field(
        default=None, alias="sni_container_refs"
    )
    insert_headers: dict[str, str] | None = Field(default=None, alias="insert_headers")
    timeout_client_data: int | None = Field(default=None, alias="timeout_client_data")
    timeout_member_connect: int | None = Field(
        default=None, alias="timeout_member_connect"
    )
    timeout_member_data: int | None = Field(default=None, alias="timeout_member_data")
    allowed_cidrs: list[str] | None = Field(default=None, alias="allowed_cidrs")
    tags: list[str] | None = None


class ListenerCreateBody(BaseModel):
    """Request body for creating a listener."""

    listener: ListenerCreateRequest


class ListenerUpdateRequest(BaseModel):
    """Request model for updating a listener."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    connection_limit: int | None = Field(default=None, alias="connection_limit")
    default_pool_id: str | None = Field(default=None, alias="default_pool_id")
    default_tls_container_ref: str | None = Field(
        default=None, alias="default_tls_container_ref"
    )
    sni_container_refs: list[str] | None = Field(
        default=None, alias="sni_container_refs"
    )
    insert_headers: dict[str, str] | None = Field(default=None, alias="insert_headers")
    timeout_client_data: int | None = Field(default=None, alias="timeout_client_data")
    timeout_member_connect: int | None = Field(
        default=None, alias="timeout_member_connect"
    )
    timeout_member_data: int | None = Field(default=None, alias="timeout_member_data")
    allowed_cidrs: list[str] | None = Field(default=None, alias="allowed_cidrs")
    tags: list[str] | None = None


class ListenerUpdateBody(BaseModel):
    """Request body for updating a listener."""

    listener: ListenerUpdateRequest


class PoolCreateRequest(BaseModel):
    """Request model for creating a pool."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    protocol: str
    lb_algorithm: str = Field(alias="lb_algorithm")
    loadbalancer_id: str | None = Field(default=None, alias="loadbalancer_id")
    listener_id: str | None = Field(default=None, alias="listener_id")
    session_persistence: dict[str, Any] | None = Field(
        default=None, alias="session_persistence"
    )
    tls_enabled: bool = Field(default=False, alias="tls_enabled")
    tags: list[str] | None = None


class PoolCreateBody(BaseModel):
    """Request body for creating a pool."""

    pool: PoolCreateRequest


class PoolUpdateRequest(BaseModel):
    """Request model for updating a pool."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    lb_algorithm: str | None = Field(default=None, alias="lb_algorithm")
    session_persistence: dict[str, Any] | None = Field(
        default=None, alias="session_persistence"
    )
    tls_enabled: bool | None = Field(default=None, alias="tls_enabled")
    tags: list[str] | None = None


class PoolUpdateBody(BaseModel):
    """Request body for updating a pool."""

    pool: PoolUpdateRequest


class MemberCreateRequest(BaseModel):
    """Request model for creating a pool member."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    address: str
    protocol_port: int = Field(alias="protocol_port")
    weight: int = 1
    subnet_id: str | None = Field(default=None, alias="subnet_id")
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    backup: bool = False
    monitor_address: str | None = Field(default=None, alias="monitor_address")
    monitor_port: int | None = Field(default=None, alias="monitor_port")
    tags: list[str] | None = None


class MemberCreateBody(BaseModel):
    """Request body for creating a pool member."""

    member: MemberCreateRequest


class MemberUpdateRequest(BaseModel):
    """Request model for updating a pool member."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    weight: int | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    backup: bool | None = None
    monitor_address: str | None = Field(default=None, alias="monitor_address")
    monitor_port: int | None = Field(default=None, alias="monitor_port")
    tags: list[str] | None = None


class MemberUpdateBody(BaseModel):
    """Request body for updating a pool member."""

    member: MemberUpdateRequest


class HealthMonitorCreateRequest(BaseModel):
    """Request model for creating a health monitor."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    type: str
    delay: int
    timeout: int
    max_retries: int = Field(alias="max_retries")
    max_retries_down: int = Field(default=3, alias="max_retries_down")
    pool_id: str = Field(alias="pool_id")
    http_method: str = Field(default="GET", alias="http_method")
    url_path: str = Field(default="/", alias="url_path")
    expected_codes: str = Field(default="200", alias="expected_codes")
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    tags: list[str] | None = None


class HealthMonitorCreateBody(BaseModel):
    """Request body for creating a health monitor."""

    healthmonitor: HealthMonitorCreateRequest


class HealthMonitorUpdateRequest(BaseModel):
    """Request model for updating a health monitor."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    delay: int | None = None
    timeout: int | None = None
    max_retries: int | None = Field(default=None, alias="max_retries")
    max_retries_down: int | None = Field(default=None, alias="max_retries_down")
    http_method: str | None = Field(default=None, alias="http_method")
    url_path: str | None = Field(default=None, alias="url_path")
    expected_codes: str | None = Field(default=None, alias="expected_codes")
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    tags: list[str] | None = None


class HealthMonitorUpdateBody(BaseModel):
    """Request body for updating a health monitor."""

    healthmonitor: HealthMonitorUpdateRequest


class L7PolicyCreateRequest(BaseModel):
    """Request model for creating an L7 policy."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    action: str
    listener_id: str = Field(alias="listener_id")
    redirect_pool_id: str | None = Field(default=None, alias="redirect_pool_id")
    redirect_url: str | None = Field(default=None, alias="redirect_url")
    redirect_prefix: str | None = Field(default=None, alias="redirect_prefix")
    redirect_http_code: int | None = Field(default=None, alias="redirect_http_code")
    position: int = 1
    tags: list[str] | None = None


class L7PolicyCreateBody(BaseModel):
    """Request body for creating an L7 policy."""

    l7policy: L7PolicyCreateRequest


class L7PolicyUpdateRequest(BaseModel):
    """Request model for updating an L7 policy."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    action: str | None = None
    redirect_pool_id: str | None = Field(default=None, alias="redirect_pool_id")
    redirect_url: str | None = Field(default=None, alias="redirect_url")
    redirect_prefix: str | None = Field(default=None, alias="redirect_prefix")
    redirect_http_code: int | None = Field(default=None, alias="redirect_http_code")
    position: int | None = None
    tags: list[str] | None = None


class L7PolicyUpdateBody(BaseModel):
    """Request body for updating an L7 policy."""

    l7policy: L7PolicyUpdateRequest


class L7RuleCreateRequest(BaseModel):
    """Request model for creating an L7 rule."""

    model_config = ConfigDict(populate_by_name=True)

    type: str
    compare_type: str = Field(alias="compare_type")
    key: str | None = None
    value: str
    invert: bool = False
    admin_state_up: bool = Field(default=True, alias="admin_state_up")
    tags: list[str] | None = None


class L7RuleCreateBody(BaseModel):
    """Request body for creating an L7 rule."""

    rule: L7RuleCreateRequest


class L7RuleUpdateRequest(BaseModel):
    """Request model for updating an L7 rule."""

    model_config = ConfigDict(populate_by_name=True)

    type: str | None = None
    compare_type: str | None = Field(default=None, alias="compare_type")
    key: str | None = None
    value: str | None = None
    invert: bool | None = None
    admin_state_up: bool | None = Field(default=None, alias="admin_state_up")
    tags: list[str] | None = None


class L7RuleUpdateBody(BaseModel):
    """Request body for updating an L7 rule."""

    rule: L7RuleUpdateRequest


# API version endpoints


@router.get("/")
async def get_versions() -> dict[str, Any]:
    """Get API versions."""
    return {
        "versions": [
            {
                "id": "v2.0",
                "status": "CURRENT",
                "links": [{"rel": "self", "href": "/v2.0"}],
            },
            {
                "id": "v2",
                "status": "SUPPORTED",
                "links": [{"rel": "self", "href": "/v2"}],
            },
        ]
    }


# Load Balancer endpoints


@router.get("/v2.0/lbaas/loadbalancers")
@router.get("/v2/lbaas/loadbalancers")
async def list_loadbalancers(
    project_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
    vip_address: str | None = Query(default=None),
    vip_subnet_id: str | None = Query(default=None),
    provisioning_status: str | None = Query(default=None),
    operating_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """List load balancers."""
    lbs = db.list_load_balancers(
        project_id=project_id,
        name=name,
        vip_address=vip_address,
        vip_subnet_id=vip_subnet_id,
        provisioning_status=provisioning_status,
        operating_status=operating_status,
    )
    return {"loadbalancers": [lb.to_dict() for lb in lbs]}


@router.post("/v2.0/lbaas/loadbalancers", status_code=201)
@router.post("/v2/lbaas/loadbalancers", status_code=201)
async def create_loadbalancer(body: LoadBalancerCreateBody) -> dict[str, Any]:
    """Create a load balancer."""
    req = body.loadbalancer
    # For emulator, use a default project_id
    project_id = "admin"

    lb = db.create_load_balancer(
        name=req.name,
        project_id=project_id,
        vip_subnet_id=req.vip_subnet_id,
        vip_network_id=req.vip_network_id,
        vip_address=req.vip_address,
        description=req.description,
        admin_state_up=req.admin_state_up,
        flavor_id=req.flavor_id,
        provider=req.provider,
        availability_zone=req.availability_zone,
        tags=req.tags,
    )
    return {"loadbalancer": lb.to_dict()}


@router.get("/v2.0/lbaas/loadbalancers/{lb_id}")
@router.get("/v2/lbaas/loadbalancers/{lb_id}")
async def get_loadbalancer(lb_id: str) -> dict[str, Any]:
    """Get a load balancer by ID."""
    lb = db.get_load_balancer(lb_id)
    if not lb:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return {"loadbalancer": lb.to_dict()}


@router.put("/v2.0/lbaas/loadbalancers/{lb_id}")
@router.put("/v2/lbaas/loadbalancers/{lb_id}")
async def update_loadbalancer(
    lb_id: str, body: LoadBalancerUpdateBody
) -> dict[str, Any]:
    """Update a load balancer."""
    req = body.loadbalancer
    lb = db.update_load_balancer(
        lb_id=lb_id,
        name=req.name,
        description=req.description,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not lb:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return {"loadbalancer": lb.to_dict()}


@router.delete("/v2.0/lbaas/loadbalancers/{lb_id}", status_code=204)
@router.delete("/v2/lbaas/loadbalancers/{lb_id}", status_code=204)
async def delete_loadbalancer(
    lb_id: str, cascade: bool = Query(default=False)
) -> None:
    """Delete a load balancer."""
    if not db.delete_load_balancer(lb_id, cascade=cascade):
        raise HTTPException(status_code=404, detail="Load balancer not found")


@router.get("/v2.0/lbaas/loadbalancers/{lb_id}/stats")
@router.get("/v2/lbaas/loadbalancers/{lb_id}/stats")
async def get_loadbalancer_stats(lb_id: str) -> dict[str, Any]:
    """Get load balancer statistics."""
    lb = db.get_load_balancer(lb_id)
    if not lb:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    # Return simulated stats
    return {
        "stats": {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0,
            "request_errors": 0,
        }
    }


@router.get("/v2.0/lbaas/loadbalancers/{lb_id}/status")
@router.get("/v2/lbaas/loadbalancers/{lb_id}/status")
async def get_loadbalancer_status(lb_id: str) -> dict[str, Any]:
    """Get load balancer status tree."""
    lb = db.get_load_balancer(lb_id)
    if not lb:
        raise HTTPException(status_code=404, detail="Load balancer not found")

    # Build status tree
    listeners_status = []
    for listener in lb.listeners:
        pools_status = []
        if listener.default_pool_id:
            pool = db.get_pool(listener.default_pool_id)
            if pool:
                members_status = [
                    {
                        "id": m.id,
                        "name": m.name,
                        "address": m.address,
                        "protocol_port": m.protocol_port,
                        "operating_status": m.operating_status.value,
                        "provisioning_status": m.provisioning_status.value,
                    }
                    for m in pool.members
                ]
                health_monitor_status = None
                if pool.healthmonitor_id:
                    hm = db.get_health_monitor(pool.healthmonitor_id)
                    if hm:
                        health_monitor_status = {
                            "id": hm.id,
                            "name": hm.name,
                            "type": hm.type.value,
                            "operating_status": hm.operating_status.value,
                            "provisioning_status": hm.provisioning_status.value,
                        }
                pools_status.append(
                    {
                        "id": pool.id,
                        "name": pool.name,
                        "operating_status": pool.operating_status.value,
                        "provisioning_status": pool.provisioning_status.value,
                        "members": members_status,
                        "healthmonitor": health_monitor_status,
                    }
                )
        listeners_status.append(
            {
                "id": listener.id,
                "name": listener.name,
                "operating_status": listener.operating_status.value,
                "provisioning_status": listener.provisioning_status.value,
                "pools": pools_status,
            }
        )

    return {
        "statuses": {
            "loadbalancer": {
                "id": lb.id,
                "name": lb.name,
                "operating_status": lb.operating_status.value,
                "provisioning_status": lb.provisioning_status.value,
                "listeners": listeners_status,
            }
        }
    }


# Listener endpoints


@router.get("/v2.0/lbaas/listeners")
@router.get("/v2/lbaas/listeners")
async def list_listeners(
    project_id: str | None = Query(default=None),
    loadbalancer_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
    protocol: str | None = Query(default=None),
    protocol_port: int | None = Query(default=None),
) -> dict[str, Any]:
    """List listeners."""
    listeners = db.list_listeners(
        project_id=project_id,
        loadbalancer_id=loadbalancer_id,
        name=name,
        protocol=protocol,
        protocol_port=protocol_port,
    )
    return {"listeners": [l.to_dict() for l in listeners]}


@router.post("/v2.0/lbaas/listeners", status_code=201)
@router.post("/v2/lbaas/listeners", status_code=201)
async def create_listener(body: ListenerCreateBody) -> dict[str, Any]:
    """Create a listener."""
    req = body.listener
    project_id = "admin"

    listener = db.create_listener(
        loadbalancer_id=req.loadbalancer_id,
        protocol=req.protocol,
        protocol_port=req.protocol_port,
        project_id=project_id,
        name=req.name,
        description=req.description,
        admin_state_up=req.admin_state_up,
        connection_limit=req.connection_limit,
        default_pool_id=req.default_pool_id,
        default_tls_container_ref=req.default_tls_container_ref,
        sni_container_refs=req.sni_container_refs,
        insert_headers=req.insert_headers,
        timeout_client_data=req.timeout_client_data,
        timeout_member_connect=req.timeout_member_connect,
        timeout_member_data=req.timeout_member_data,
        allowed_cidrs=req.allowed_cidrs,
        tags=req.tags,
    )
    if not listener:
        raise HTTPException(status_code=404, detail="Load balancer not found")
    return {"listener": listener.to_dict()}


@router.get("/v2.0/lbaas/listeners/{listener_id}")
@router.get("/v2/lbaas/listeners/{listener_id}")
async def get_listener(listener_id: str) -> dict[str, Any]:
    """Get a listener by ID."""
    listener = db.get_listener(listener_id)
    if not listener:
        raise HTTPException(status_code=404, detail="Listener not found")
    return {"listener": listener.to_dict()}


@router.put("/v2.0/lbaas/listeners/{listener_id}")
@router.put("/v2/lbaas/listeners/{listener_id}")
async def update_listener(
    listener_id: str, body: ListenerUpdateBody
) -> dict[str, Any]:
    """Update a listener."""
    req = body.listener
    listener = db.update_listener(
        listener_id=listener_id,
        name=req.name,
        description=req.description,
        admin_state_up=req.admin_state_up,
        connection_limit=req.connection_limit,
        default_pool_id=req.default_pool_id,
        default_tls_container_ref=req.default_tls_container_ref,
        sni_container_refs=req.sni_container_refs,
        insert_headers=req.insert_headers,
        timeout_client_data=req.timeout_client_data,
        timeout_member_connect=req.timeout_member_connect,
        timeout_member_data=req.timeout_member_data,
        allowed_cidrs=req.allowed_cidrs,
        tags=req.tags,
    )
    if not listener:
        raise HTTPException(status_code=404, detail="Listener not found")
    return {"listener": listener.to_dict()}


@router.delete("/v2.0/lbaas/listeners/{listener_id}", status_code=204)
@router.delete("/v2/lbaas/listeners/{listener_id}", status_code=204)
async def delete_listener(listener_id: str) -> None:
    """Delete a listener."""
    if not db.delete_listener(listener_id):
        raise HTTPException(status_code=404, detail="Listener not found")


@router.get("/v2.0/lbaas/listeners/{listener_id}/stats")
@router.get("/v2/lbaas/listeners/{listener_id}/stats")
async def get_listener_stats(listener_id: str) -> dict[str, Any]:
    """Get listener statistics."""
    listener = db.get_listener(listener_id)
    if not listener:
        raise HTTPException(status_code=404, detail="Listener not found")
    return {
        "stats": {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0,
            "request_errors": 0,
        }
    }


# Pool endpoints


@router.get("/v2.0/lbaas/pools")
@router.get("/v2/lbaas/pools")
async def list_pools(
    project_id: str | None = Query(default=None),
    loadbalancer_id: str | None = Query(default=None),
    listener_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
    protocol: str | None = Query(default=None),
) -> dict[str, Any]:
    """List pools."""
    pools = db.list_pools(
        project_id=project_id,
        loadbalancer_id=loadbalancer_id,
        listener_id=listener_id,
        name=name,
        protocol=protocol,
    )
    return {"pools": [p.to_dict() for p in pools]}


@router.post("/v2.0/lbaas/pools", status_code=201)
@router.post("/v2/lbaas/pools", status_code=201)
async def create_pool(body: PoolCreateBody) -> dict[str, Any]:
    """Create a pool."""
    req = body.pool
    project_id = "admin"

    pool = db.create_pool(
        protocol=req.protocol,
        lb_algorithm=req.lb_algorithm,
        project_id=project_id,
        loadbalancer_id=req.loadbalancer_id,
        listener_id=req.listener_id,
        name=req.name,
        description=req.description,
        admin_state_up=req.admin_state_up,
        session_persistence=req.session_persistence,
        tls_enabled=req.tls_enabled,
        tags=req.tags,
    )
    if not pool:
        raise HTTPException(status_code=400, detail="Failed to create pool")
    return {"pool": pool.to_dict()}


@router.get("/v2.0/lbaas/pools/{pool_id}")
@router.get("/v2/lbaas/pools/{pool_id}")
async def get_pool(pool_id: str) -> dict[str, Any]:
    """Get a pool by ID."""
    pool = db.get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {"pool": pool.to_dict()}


@router.put("/v2.0/lbaas/pools/{pool_id}")
@router.put("/v2/lbaas/pools/{pool_id}")
async def update_pool(pool_id: str, body: PoolUpdateBody) -> dict[str, Any]:
    """Update a pool."""
    req = body.pool
    pool = db.update_pool(
        pool_id=pool_id,
        name=req.name,
        description=req.description,
        admin_state_up=req.admin_state_up,
        lb_algorithm=req.lb_algorithm,
        session_persistence=req.session_persistence,
        tls_enabled=req.tls_enabled,
        tags=req.tags,
    )
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {"pool": pool.to_dict()}


@router.delete("/v2.0/lbaas/pools/{pool_id}", status_code=204)
@router.delete("/v2/lbaas/pools/{pool_id}", status_code=204)
async def delete_pool(pool_id: str) -> None:
    """Delete a pool."""
    if not db.delete_pool(pool_id):
        raise HTTPException(status_code=404, detail="Pool not found")


# Pool Member endpoints


@router.get("/v2.0/lbaas/pools/{pool_id}/members")
@router.get("/v2/lbaas/pools/{pool_id}/members")
async def list_members(
    pool_id: str,
    project_id: str | None = Query(default=None),
    address: str | None = Query(default=None),
    protocol_port: int | None = Query(default=None),
) -> dict[str, Any]:
    """List pool members."""
    members = db.list_pool_members(
        pool_id=pool_id,
        project_id=project_id,
        address=address,
        protocol_port=protocol_port,
    )
    return {"members": [m.to_dict() for m in members]}


@router.post("/v2.0/lbaas/pools/{pool_id}/members", status_code=201)
@router.post("/v2/lbaas/pools/{pool_id}/members", status_code=201)
async def create_member(pool_id: str, body: MemberCreateBody) -> dict[str, Any]:
    """Create a pool member."""
    req = body.member
    project_id = "admin"

    member = db.create_pool_member(
        pool_id=pool_id,
        address=req.address,
        protocol_port=req.protocol_port,
        project_id=project_id,
        name=req.name,
        weight=req.weight,
        subnet_id=req.subnet_id,
        admin_state_up=req.admin_state_up,
        backup=req.backup,
        monitor_address=req.monitor_address,
        monitor_port=req.monitor_port,
        tags=req.tags,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {"member": member.to_dict()}


@router.get("/v2.0/lbaas/pools/{pool_id}/members/{member_id}")
@router.get("/v2/lbaas/pools/{pool_id}/members/{member_id}")
async def get_member(pool_id: str, member_id: str) -> dict[str, Any]:
    """Get a pool member by ID."""
    member = db.get_pool_member(pool_id, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"member": member.to_dict()}


@router.put("/v2.0/lbaas/pools/{pool_id}/members/{member_id}")
@router.put("/v2/lbaas/pools/{pool_id}/members/{member_id}")
async def update_member(
    pool_id: str, member_id: str, body: MemberUpdateBody
) -> dict[str, Any]:
    """Update a pool member."""
    req = body.member
    member = db.update_pool_member(
        pool_id=pool_id,
        member_id=member_id,
        name=req.name,
        weight=req.weight,
        admin_state_up=req.admin_state_up,
        backup=req.backup,
        monitor_address=req.monitor_address,
        monitor_port=req.monitor_port,
        tags=req.tags,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"member": member.to_dict()}


@router.delete("/v2.0/lbaas/pools/{pool_id}/members/{member_id}", status_code=204)
@router.delete("/v2/lbaas/pools/{pool_id}/members/{member_id}", status_code=204)
async def delete_member(pool_id: str, member_id: str) -> None:
    """Delete a pool member."""
    if not db.delete_pool_member(pool_id, member_id):
        raise HTTPException(status_code=404, detail="Member not found")


# Health Monitor endpoints


@router.get("/v2.0/lbaas/healthmonitors")
@router.get("/v2/lbaas/healthmonitors")
async def list_healthmonitors(
    project_id: str | None = Query(default=None),
    pool_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
) -> dict[str, Any]:
    """List health monitors."""
    monitors = db.list_health_monitors(
        project_id=project_id,
        pool_id=pool_id,
        type=type,
    )
    return {"healthmonitors": [m.to_dict() for m in monitors]}


@router.post("/v2.0/lbaas/healthmonitors", status_code=201)
@router.post("/v2/lbaas/healthmonitors", status_code=201)
async def create_healthmonitor(body: HealthMonitorCreateBody) -> dict[str, Any]:
    """Create a health monitor."""
    req = body.healthmonitor
    project_id = "admin"

    monitor = db.create_health_monitor(
        pool_id=req.pool_id,
        type=req.type,
        delay=req.delay,
        timeout=req.timeout,
        max_retries=req.max_retries,
        project_id=project_id,
        name=req.name,
        max_retries_down=req.max_retries_down,
        http_method=req.http_method,
        url_path=req.url_path,
        expected_codes=req.expected_codes,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not monitor:
        raise HTTPException(
            status_code=400,
            detail="Failed to create health monitor (pool not found or already has one)",
        )
    return {"healthmonitor": monitor.to_dict()}


@router.get("/v2.0/lbaas/healthmonitors/{healthmonitor_id}")
@router.get("/v2/lbaas/healthmonitors/{healthmonitor_id}")
async def get_healthmonitor(healthmonitor_id: str) -> dict[str, Any]:
    """Get a health monitor by ID."""
    monitor = db.get_health_monitor(healthmonitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Health monitor not found")
    return {"healthmonitor": monitor.to_dict()}


@router.put("/v2.0/lbaas/healthmonitors/{healthmonitor_id}")
@router.put("/v2/lbaas/healthmonitors/{healthmonitor_id}")
async def update_healthmonitor(
    healthmonitor_id: str, body: HealthMonitorUpdateBody
) -> dict[str, Any]:
    """Update a health monitor."""
    req = body.healthmonitor
    monitor = db.update_health_monitor(
        monitor_id=healthmonitor_id,
        name=req.name,
        delay=req.delay,
        timeout=req.timeout,
        max_retries=req.max_retries,
        max_retries_down=req.max_retries_down,
        http_method=req.http_method,
        url_path=req.url_path,
        expected_codes=req.expected_codes,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Health monitor not found")
    return {"healthmonitor": monitor.to_dict()}


@router.delete("/v2.0/lbaas/healthmonitors/{healthmonitor_id}", status_code=204)
@router.delete("/v2/lbaas/healthmonitors/{healthmonitor_id}", status_code=204)
async def delete_healthmonitor(healthmonitor_id: str) -> None:
    """Delete a health monitor."""
    if not db.delete_health_monitor(healthmonitor_id):
        raise HTTPException(status_code=404, detail="Health monitor not found")


# L7 Policy endpoints


@router.get("/v2.0/lbaas/l7policies")
@router.get("/v2/lbaas/l7policies")
async def list_l7policies(
    project_id: str | None = Query(default=None),
    listener_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
) -> dict[str, Any]:
    """List L7 policies."""
    policies = db.list_l7policies(
        project_id=project_id,
        listener_id=listener_id,
        action=action,
    )
    return {"l7policies": [p.to_dict() for p in policies]}


@router.post("/v2.0/lbaas/l7policies", status_code=201)
@router.post("/v2/lbaas/l7policies", status_code=201)
async def create_l7policy(body: L7PolicyCreateBody) -> dict[str, Any]:
    """Create an L7 policy."""
    req = body.l7policy
    project_id = "admin"

    policy = db.create_l7policy(
        listener_id=req.listener_id,
        action=req.action,
        project_id=project_id,
        name=req.name,
        description=req.description,
        redirect_pool_id=req.redirect_pool_id,
        redirect_url=req.redirect_url,
        redirect_prefix=req.redirect_prefix,
        redirect_http_code=req.redirect_http_code,
        position=req.position,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Listener not found")
    return {"l7policy": policy.to_dict()}


@router.get("/v2.0/lbaas/l7policies/{l7policy_id}")
@router.get("/v2/lbaas/l7policies/{l7policy_id}")
async def get_l7policy(l7policy_id: str) -> dict[str, Any]:
    """Get an L7 policy by ID."""
    policy = db.get_l7policy(l7policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="L7 policy not found")
    return {"l7policy": policy.to_dict()}


@router.put("/v2.0/lbaas/l7policies/{l7policy_id}")
@router.put("/v2/lbaas/l7policies/{l7policy_id}")
async def update_l7policy(
    l7policy_id: str, body: L7PolicyUpdateBody
) -> dict[str, Any]:
    """Update an L7 policy."""
    req = body.l7policy
    policy = db.update_l7policy(
        policy_id=l7policy_id,
        name=req.name,
        description=req.description,
        action=req.action,
        redirect_pool_id=req.redirect_pool_id,
        redirect_url=req.redirect_url,
        redirect_prefix=req.redirect_prefix,
        redirect_http_code=req.redirect_http_code,
        position=req.position,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not policy:
        raise HTTPException(status_code=404, detail="L7 policy not found")
    return {"l7policy": policy.to_dict()}


@router.delete("/v2.0/lbaas/l7policies/{l7policy_id}", status_code=204)
@router.delete("/v2/lbaas/l7policies/{l7policy_id}", status_code=204)
async def delete_l7policy(l7policy_id: str) -> None:
    """Delete an L7 policy."""
    if not db.delete_l7policy(l7policy_id):
        raise HTTPException(status_code=404, detail="L7 policy not found")


# L7 Rule endpoints


@router.get("/v2.0/lbaas/l7policies/{l7policy_id}/rules")
@router.get("/v2/lbaas/l7policies/{l7policy_id}/rules")
async def list_l7rules(
    l7policy_id: str,
    project_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
) -> dict[str, Any]:
    """List L7 rules."""
    rules = db.list_l7rules(
        l7policy_id=l7policy_id,
        project_id=project_id,
        type=type,
    )
    return {"rules": [r.to_dict() for r in rules]}


@router.post("/v2.0/lbaas/l7policies/{l7policy_id}/rules", status_code=201)
@router.post("/v2/lbaas/l7policies/{l7policy_id}/rules", status_code=201)
async def create_l7rule(l7policy_id: str, body: L7RuleCreateBody) -> dict[str, Any]:
    """Create an L7 rule."""
    req = body.rule
    project_id = "admin"

    rule = db.create_l7rule(
        l7policy_id=l7policy_id,
        type=req.type,
        compare_type=req.compare_type,
        value=req.value,
        project_id=project_id,
        key=req.key,
        invert=req.invert,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="L7 policy not found")
    return {"rule": rule.to_dict()}


@router.get("/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
@router.get("/v2/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
async def get_l7rule(l7policy_id: str, rule_id: str) -> dict[str, Any]:
    """Get an L7 rule by ID."""
    rule = db.get_l7rule(l7policy_id, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="L7 rule not found")
    return {"rule": rule.to_dict()}


@router.put("/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
@router.put("/v2/lbaas/l7policies/{l7policy_id}/rules/{rule_id}")
async def update_l7rule(
    l7policy_id: str, rule_id: str, body: L7RuleUpdateBody
) -> dict[str, Any]:
    """Update an L7 rule."""
    req = body.rule
    rule = db.update_l7rule(
        l7policy_id=l7policy_id,
        rule_id=rule_id,
        type=req.type,
        compare_type=req.compare_type,
        key=req.key,
        value=req.value,
        invert=req.invert,
        admin_state_up=req.admin_state_up,
        tags=req.tags,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="L7 rule not found")
    return {"rule": rule.to_dict()}


@router.delete("/v2.0/lbaas/l7policies/{l7policy_id}/rules/{rule_id}", status_code=204)
@router.delete("/v2/lbaas/l7policies/{l7policy_id}/rules/{rule_id}", status_code=204)
async def delete_l7rule(l7policy_id: str, rule_id: str) -> None:
    """Delete an L7 rule."""
    if not db.delete_l7rule(l7policy_id, rule_id):
        raise HTTPException(status_code=404, detail="L7 rule not found")
