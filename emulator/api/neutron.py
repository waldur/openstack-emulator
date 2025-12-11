"""Neutron Networking API v2 endpoints for OpenStack emulator.

Implements the OpenStack Neutron Networking Service API v2.0.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db

router = APIRouter()


# Pydantic models for requests/responses
class NetworkRequest(BaseModel):
    """Request model for creating/updating a network."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool = True
    shared: bool = False
    router_external: bool = Field(default=False, alias="router:external")
    mtu: int | None = None
    port_security_enabled: bool = True


class SubnetRequest(BaseModel):
    """Request model for creating/updating a subnet."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    network_id: str | None = None
    ip_version: int = 4
    cidr: str | None = None
    gateway_ip: str | None = None
    allocation_pools: list[dict[str, str]] | None = None
    dns_nameservers: list[str] | None = None
    host_routes: list[dict[str, str]] | None = None
    enable_dhcp: bool = True


class PortRequest(BaseModel):
    """Request model for creating/updating a port."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    network_id: str | None = None
    admin_state_up: bool = True
    mac_address: str | None = None
    fixed_ips: list[dict[str, str]] | None = None
    device_id: str | None = None
    device_owner: str | None = None
    security_groups: list[str] | None = None
    port_security_enabled: bool = True


class RouterRequest(BaseModel):
    """Request model for creating/updating a router."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    admin_state_up: bool = True
    external_gateway_info: dict[str, Any] | None = None


class FloatingIPRequest(BaseModel):
    """Request model for creating/updating a floating IP."""

    model_config = ConfigDict(populate_by_name=True)

    floating_network_id: str | None = None
    description: str | None = None
    port_id: str | None = None
    fixed_ip_address: str | None = None
    floating_ip_address: str | None = None


class SecurityGroupRequest(BaseModel):
    """Request model for creating/updating a security group."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None


class SecurityGroupRuleRequest(BaseModel):
    """Request model for creating a security group rule."""

    model_config = ConfigDict(populate_by_name=True)

    security_group_id: str
    direction: str
    ethertype: str = "IPv4"
    protocol: str | None = None
    port_range_min: int | None = None
    port_range_max: int | None = None
    remote_ip_prefix: str | None = None
    remote_group_id: str | None = None
    description: str | None = None


class RouterInterfaceRequest(BaseModel):
    """Request model for adding/removing router interface."""

    model_config = ConfigDict(populate_by_name=True)

    subnet_id: str | None = None
    port_id: str | None = None


# Helper functions
def _get_project_id(token: str | None) -> str:
    """Extract project ID from token."""
    if not token:
        return "admin"
    token_data = db.validate_token(token)
    if token_data:
        return token_data.project_id
    return "admin"


# API Version endpoint
@router.get("/")
async def get_versions() -> dict[str, Any]:
    """Get available API versions."""
    return {
        "versions": [
            {
                "id": "v2.0",
                "status": "CURRENT",
                "links": [{"rel": "self", "href": "/v2.0/"}],
            },
        ]
    }


# Networks
@router.get("/v2.0/networks")
async def list_networks(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    name: str | None = Query(None),
    shared: bool | None = Query(None),
    router_external: bool | None = Query(None, alias="router:external"),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """List networks."""
    project_id = _get_project_id(x_auth_token)
    networks = db.list_networks(
        project_id=project_id,
        name=name,
        shared=shared,
        external=router_external,
        status=status,
    )
    return {"networks": [n.to_dict() for n in networks]}


@router.post("/v2.0/networks", status_code=201)
async def create_network(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a network."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("network", {})

    network = db.create_network(
        name=data.get("name", ""),
        project_id=project_id,
        description=data.get("description", ""),
        admin_state_up=data.get("admin_state_up", True),
        shared=data.get("shared", False),
        external=data.get("router:external", False),
        mtu=data.get("mtu", 1500),
        port_security_enabled=data.get("port_security_enabled", True),
    )
    return {"network": network.to_dict()}


@router.get("/v2.0/networks/{network_id}")
async def get_network(
    network_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get network details."""
    network = db.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"network": network.to_dict()}


@router.put("/v2.0/networks/{network_id}")
async def update_network(
    network_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a network."""
    data = request.get("network", {})
    network = db.update_network(
        network_id=network_id,
        name=data.get("name"),
        description=data.get("description"),
        admin_state_up=data.get("admin_state_up"),
        shared=data.get("shared"),
        port_security_enabled=data.get("port_security_enabled"),
    )
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"network": network.to_dict()}


@router.delete("/v2.0/networks/{network_id}", status_code=204, response_model=None)
async def delete_network(
    network_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a network."""
    success = db.delete_network(network_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete network (may have ports)")
    return Response(status_code=204)


# Subnets
@router.get("/v2.0/subnets")
async def list_subnets(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    network_id: str | None = Query(None),
    name: str | None = Query(None),
) -> dict[str, Any]:
    """List subnets."""
    project_id = _get_project_id(x_auth_token)
    subnets = db.list_subnets(project_id=project_id, network_id=network_id, name=name)
    return {"subnets": [s.to_dict() for s in subnets]}


@router.post("/v2.0/subnets", status_code=201)
async def create_subnet(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a subnet."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("subnet", {})

    subnet = db.create_subnet(
        network_id=data.get("network_id", ""),
        cidr=data.get("cidr", ""),
        project_id=project_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        ip_version=data.get("ip_version", 4),
        gateway_ip=data.get("gateway_ip"),
        allocation_pools=data.get("allocation_pools"),
        dns_nameservers=data.get("dns_nameservers"),
        host_routes=data.get("host_routes"),
        enable_dhcp=data.get("enable_dhcp", True),
    )
    if not subnet:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"subnet": subnet.to_dict()}


@router.get("/v2.0/subnets/{subnet_id}")
async def get_subnet(
    subnet_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get subnet details."""
    subnet = db.get_subnet(subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return {"subnet": subnet.to_dict()}


@router.put("/v2.0/subnets/{subnet_id}")
async def update_subnet(
    subnet_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a subnet."""
    data = request.get("subnet", {})
    subnet = db.update_subnet(
        subnet_id=subnet_id,
        name=data.get("name"),
        description=data.get("description"),
        gateway_ip=data.get("gateway_ip"),
        dns_nameservers=data.get("dns_nameservers"),
        host_routes=data.get("host_routes"),
        enable_dhcp=data.get("enable_dhcp"),
    )
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return {"subnet": subnet.to_dict()}


@router.delete("/v2.0/subnets/{subnet_id}", status_code=204, response_model=None)
async def delete_subnet(
    subnet_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a subnet."""
    success = db.delete_subnet(subnet_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete subnet (may have ports)")
    return Response(status_code=204)


# Ports
@router.get("/v2.0/ports")
async def list_ports(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    network_id: str | None = Query(None),
    device_id: str | None = Query(None),
    device_owner: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """List ports."""
    project_id = _get_project_id(x_auth_token)
    ports = db.list_ports(
        project_id=project_id,
        network_id=network_id,
        device_id=device_id,
        device_owner=device_owner,
        status=status,
    )
    return {"ports": [p.to_dict() for p in ports]}


@router.post("/v2.0/ports", status_code=201)
async def create_port(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a port."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("port", {})

    port = db.create_port(
        network_id=data.get("network_id", ""),
        project_id=project_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        admin_state_up=data.get("admin_state_up", True),
        mac_address=data.get("mac_address"),
        fixed_ips=data.get("fixed_ips"),
        device_id=data.get("device_id", ""),
        device_owner=data.get("device_owner", ""),
        security_groups=data.get("security_groups"),
        port_security_enabled=data.get("port_security_enabled", True),
    )
    if not port:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"port": port.to_dict()}


@router.get("/v2.0/ports/{port_id}")
async def get_port(
    port_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get port details."""
    port = db.get_port(port_id)
    if not port:
        raise HTTPException(status_code=404, detail="Port not found")
    return {"port": port.to_dict()}


@router.put("/v2.0/ports/{port_id}")
async def update_port(
    port_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a port."""
    data = request.get("port", {})
    port = db.update_port(
        port_id=port_id,
        name=data.get("name"),
        description=data.get("description"),
        admin_state_up=data.get("admin_state_up"),
        device_id=data.get("device_id"),
        device_owner=data.get("device_owner"),
        security_groups=data.get("security_groups"),
        port_security_enabled=data.get("port_security_enabled"),
    )
    if not port:
        raise HTTPException(status_code=404, detail="Port not found")
    return {"port": port.to_dict()}


@router.delete("/v2.0/ports/{port_id}", status_code=204, response_model=None)
async def delete_port(
    port_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a port."""
    success = db.delete_port(port_id)
    if not success:
        raise HTTPException(status_code=404, detail="Port not found")
    return Response(status_code=204)


# Routers
@router.get("/v2.0/routers")
async def list_routers(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    name: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """List routers."""
    project_id = _get_project_id(x_auth_token)
    routers = db.list_routers(project_id=project_id, name=name, status=status)
    return {"routers": [r.to_dict() for r in routers]}


@router.post("/v2.0/routers", status_code=201)
async def create_router(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a router."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("router", {})

    router = db.create_router(
        name=data.get("name", ""),
        project_id=project_id,
        description=data.get("description", ""),
        admin_state_up=data.get("admin_state_up", True),
        external_gateway_info=data.get("external_gateway_info"),
    )
    return {"router": router.to_dict()}


@router.get("/v2.0/routers/{router_id}")
async def get_router(
    router_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get router details."""
    router = db.get_router(router_id)
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    return {"router": router.to_dict()}


@router.put("/v2.0/routers/{router_id}")
async def update_router(
    router_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a router."""
    data = request.get("router", {})
    router = db.update_router(
        router_id=router_id,
        name=data.get("name"),
        description=data.get("description"),
        admin_state_up=data.get("admin_state_up"),
        external_gateway_info=data.get("external_gateway_info"),
        routes=data.get("routes"),
    )
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    return {"router": router.to_dict()}


@router.delete("/v2.0/routers/{router_id}", status_code=204, response_model=None)
async def delete_router(
    router_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a router."""
    success = db.delete_router(router_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete router (may have interfaces)")
    return Response(status_code=204)


@router.put("/v2.0/routers/{router_id}/add_router_interface")
async def add_router_interface(
    router_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Add interface to router."""
    result = db.add_router_interface(
        router_id=router_id,
        subnet_id=request.get("subnet_id"),
        port_id=request.get("port_id"),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Router or subnet not found")
    return result


@router.put("/v2.0/routers/{router_id}/remove_router_interface")
async def remove_router_interface(
    router_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Remove interface from router."""
    result = db.remove_router_interface(
        router_id=router_id,
        subnet_id=request.get("subnet_id"),
        port_id=request.get("port_id"),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Router or interface not found")
    return result


# Floating IPs
@router.get("/v2.0/floatingips")
async def list_floating_ips(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    floating_network_id: str | None = Query(None),
    port_id: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """List floating IPs."""
    project_id = _get_project_id(x_auth_token)
    fips = db.list_floating_ips(
        project_id=project_id,
        floating_network_id=floating_network_id,
        port_id=port_id,
        status=status,
    )
    return {"floatingips": [f.to_dict() for f in fips]}


@router.post("/v2.0/floatingips", status_code=201)
async def create_floating_ip(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a floating IP."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("floatingip", {})

    fip = db.create_floating_ip(
        floating_network_id=data.get("floating_network_id", ""),
        project_id=project_id,
        description=data.get("description", ""),
        port_id=data.get("port_id"),
        fixed_ip_address=data.get("fixed_ip_address"),
        floating_ip_address=data.get("floating_ip_address"),
    )
    if not fip:
        raise HTTPException(status_code=404, detail="External network not found")
    return {"floatingip": fip.to_dict()}


@router.get("/v2.0/floatingips/{floatingip_id}")
async def get_floating_ip(
    floatingip_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get floating IP details."""
    fip = db.get_floating_ip(floatingip_id)
    if not fip:
        raise HTTPException(status_code=404, detail="Floating IP not found")
    return {"floatingip": fip.to_dict()}


@router.put("/v2.0/floatingips/{floatingip_id}")
async def update_floating_ip(
    floatingip_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a floating IP (associate/disassociate)."""
    data = request.get("floatingip", {})
    fip = db.update_floating_ip(
        floatingip_id=floatingip_id,
        description=data.get("description"),
        port_id=data.get("port_id"),
    )
    if not fip:
        raise HTTPException(status_code=404, detail="Floating IP not found")
    return {"floatingip": fip.to_dict()}


@router.delete("/v2.0/floatingips/{floatingip_id}", status_code=204, response_model=None)
async def delete_floating_ip(
    floatingip_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a floating IP."""
    success = db.delete_floating_ip(floatingip_id)
    if not success:
        raise HTTPException(status_code=404, detail="Floating IP not found")
    return Response(status_code=204)


# Security Groups
@router.get("/v2.0/security-groups")
async def list_security_groups(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    name: str | None = Query(None),
) -> dict[str, Any]:
    """List security groups."""
    project_id = _get_project_id(x_auth_token)
    sgs = db.list_security_groups(project_id=project_id, name=name)
    return {"security_groups": [sg.to_dict() for sg in sgs]}


@router.post("/v2.0/security-groups", status_code=201)
async def create_security_group(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a security group."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("security_group", {})

    sg = db.create_security_group(
        name=data.get("name", ""),
        project_id=project_id,
        description=data.get("description", ""),
    )
    return {"security_group": sg.to_dict()}


@router.get("/v2.0/security-groups/{security_group_id}")
async def get_security_group(
    security_group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get security group details."""
    sg = db.get_security_group(security_group_id)
    if not sg:
        raise HTTPException(status_code=404, detail="Security group not found")
    return {"security_group": sg.to_dict()}


@router.put("/v2.0/security-groups/{security_group_id}")
async def update_security_group(
    security_group_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a security group."""
    data = request.get("security_group", {})
    sg = db.update_security_group(
        security_group_id=security_group_id,
        name=data.get("name"),
        description=data.get("description"),
    )
    if not sg:
        raise HTTPException(status_code=404, detail="Security group not found")
    return {"security_group": sg.to_dict()}


@router.delete("/v2.0/security-groups/{security_group_id}", status_code=204, response_model=None)
async def delete_security_group(
    security_group_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a security group."""
    success = db.delete_security_group(security_group_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete security group")
    return Response(status_code=204)


# Security Group Rules
@router.get("/v2.0/security-group-rules")
async def list_security_group_rules(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    security_group_id: str | None = Query(None),
) -> dict[str, Any]:
    """List security group rules."""
    project_id = _get_project_id(x_auth_token)
    rules = db.list_security_group_rules(
        project_id=project_id,
        security_group_id=security_group_id,
    )
    return {"security_group_rules": [r.to_dict() for r in rules]}


@router.post("/v2.0/security-group-rules", status_code=201)
async def create_security_group_rule(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a security group rule."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("security_group_rule", {})

    rule = db.create_security_group_rule(
        security_group_id=data.get("security_group_id", ""),
        direction=data.get("direction", "ingress"),
        project_id=project_id,
        ethertype=data.get("ethertype", "IPv4"),
        protocol=data.get("protocol"),
        port_range_min=data.get("port_range_min"),
        port_range_max=data.get("port_range_max"),
        remote_ip_prefix=data.get("remote_ip_prefix"),
        remote_group_id=data.get("remote_group_id"),
        description=data.get("description", ""),
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Security group not found")
    return {"security_group_rule": rule.to_dict()}


@router.get("/v2.0/security-group-rules/{rule_id}")
async def get_security_group_rule(
    rule_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get security group rule details."""
    rule = db.get_security_group_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Security group rule not found")
    return {"security_group_rule": rule.to_dict()}


@router.delete("/v2.0/security-group-rules/{rule_id}", status_code=204, response_model=None)
async def delete_security_group_rule(
    rule_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a security group rule."""
    success = db.delete_security_group_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Security group rule not found")
    return Response(status_code=204)


# ==================== Quotas ====================


@router.get("/v2.0/quotas/{project_id}")
async def get_quota(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get network quota for a project."""
    quota = db.get_neutron_quota(project_id)
    return {"quota": quota.to_dict()}


@router.get("/v2.0/quotas/{project_id}/details")
async def get_quota_details(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get detailed network quota with usage for a project."""
    quota = db.get_neutron_quota(project_id)
    usage = db.get_neutron_quota_usage(project_id)
    return {"quota": quota.to_detail_dict(usage)}


@router.put("/v2.0/quotas/{project_id}")
async def update_quota(
    project_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update network quota for a project."""
    body = await request.json()
    quota_data = body.get("quota", {})

    quota = db.update_neutron_quota(
        project_id=project_id,
        network=quota_data.get("network"),
        subnet=quota_data.get("subnet"),
        subnetpool=quota_data.get("subnetpool"),
        port=quota_data.get("port"),
        router=quota_data.get("router"),
        floatingip=quota_data.get("floatingip"),
        security_group=quota_data.get("security_group"),
        security_group_rule=quota_data.get("security_group_rule"),
        rbac_policy=quota_data.get("rbac_policy"),
    )

    return {"quota": quota.to_dict()}


@router.delete("/v2.0/quotas/{project_id}", status_code=204, response_model=None)
async def delete_quota(
    project_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete (reset) network quota for a project."""
    db.delete_neutron_quota(project_id)
    return Response(status_code=204)


@router.get("/v2.0/quotas")
async def list_quotas(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List all quotas (returns default quota)."""
    # Return default quota values
    from emulator.core.models import NeutronQuota
    default_quota = NeutronQuota()
    return {"quotas": [default_quota.to_dict()]}


# Extensions endpoint
@router.get("/v2.0/extensions")
async def list_extensions() -> dict[str, Any]:
    """List available extensions."""
    return {
        "extensions": [
            {
                "alias": "security-group",
                "description": "Security group support",
                "name": "security-group",
                "updated": "2023-01-01T00:00:00-00:00",
            },
            {
                "alias": "router",
                "description": "Router support",
                "name": "router",
                "updated": "2023-01-01T00:00:00-00:00",
            },
            {
                "alias": "external-net",
                "description": "External network support",
                "name": "external-net",
                "updated": "2023-01-01T00:00:00-00:00",
            },
            {
                "alias": "quotas",
                "description": "Quota management support",
                "name": "quotas",
                "updated": "2023-01-01T00:00:00-00:00",
            },
        ]
    }
