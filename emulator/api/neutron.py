"""Neutron Networking API v2 endpoints for OpenStack emulator.

Implements the OpenStack Neutron Networking Service API v2.0.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple

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
    try:
        token_data = validate_token_simple(token, "Neutron")
        return token_data.project_id
    except HTTPException:
        return "admin"  # Fallback for development


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
    """Get network details.

    Shared and external networks are accessible to all tenants.
    """
    project_id = _get_project_id(x_auth_token)
    network = db.get_network(network_id, project_id=project_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"network": network.to_dict()}


@router.put("/v2.0/networks/{network_id}")
async def update_network(
    network_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a network.

    Only allows updating networks owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("network", {})
    network = db.update_network(
        network_id=network_id,
        project_id=project_id,
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
    """Delete a network.

    Only allows deleting networks owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_network(network_id, project_id=project_id)
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
    """Get subnet details.

    Subnets on shared/external networks are accessible to all tenants.
    """
    project_id = _get_project_id(x_auth_token)
    subnet = db.get_subnet(subnet_id, project_id=project_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return {"subnet": subnet.to_dict()}


@router.put("/v2.0/subnets/{subnet_id}")
async def update_subnet(
    subnet_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a subnet.

    Only allows updating subnets owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("subnet", {})
    subnet = db.update_subnet(
        subnet_id=subnet_id,
        project_id=project_id,
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
    """Delete a subnet.

    Only allows deleting subnets owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_subnet(subnet_id, project_id=project_id)
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
    """Get port details.

    Only returns ports owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    port = db.get_port(port_id, project_id=project_id)
    if not port:
        raise HTTPException(status_code=404, detail="Port not found")
    return {"port": port.to_dict()}


@router.put("/v2.0/ports/{port_id}")
async def update_port(
    port_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a port.

    Only allows updating ports owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("port", {})
    port = db.update_port(
        port_id=port_id,
        project_id=project_id,
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
    """Delete a port.

    Only allows deleting ports owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_port(port_id, project_id=project_id)
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


def _validate_external_gateway(
    project_id: str, external_gateway_info: dict[str, Any] | None
) -> None:
    """Validate a router's external gateway request.

    A gateway network must exist, be visible to the requesting project, and be
    usable as an external network for that project (either globally external or
    shared to it via an ``access_as_external`` RBAC policy). Raises HTTPException
    on failure; a falsy ``external_gateway_info`` (gateway removal) is a no-op.
    """
    if not external_gateway_info:
        return
    network_id = external_gateway_info.get("network_id")
    if not network_id:
        return
    if db.get_network(network_id, project_id=project_id) is None:
        raise HTTPException(status_code=404, detail="External network not found")
    if not db.is_network_external_for(network_id, project_id):
        raise HTTPException(
            status_code=400,
            detail="Network is not usable as an external gateway for this project",
        )


@router.post("/v2.0/routers", status_code=201)
async def create_router(
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a router."""
    project_id = _get_project_id(x_auth_token)
    data = request.get("router", {})

    _validate_external_gateway(project_id, data.get("external_gateway_info"))

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
    """Get router details.

    Only returns routers owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    router = db.get_router(router_id, project_id=project_id)
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    return {"router": router.to_dict()}


@router.put("/v2.0/routers/{router_id}")
async def update_router(
    router_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a router.

    Only allows updating routers owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("router", {})

    _validate_external_gateway(project_id, data.get("external_gateway_info"))

    router = db.update_router(
        router_id=router_id,
        project_id=project_id,
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
    """Delete a router.

    Only allows deleting routers owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_router(router_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=409, detail="Cannot delete router (may have interfaces)")
    return Response(status_code=204)


@router.put("/v2.0/routers/{router_id}/add_router_interface")
async def add_router_interface(
    router_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Add interface to router.

    Only allows modifying routers owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    result = db.add_router_interface(
        router_id=router_id,
        project_id=project_id,
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
    """Remove interface from router.

    Only allows modifying routers owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    result = db.remove_router_interface(
        router_id=router_id,
        project_id=project_id,
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
    """Get floating IP details.

    Only returns floating IPs owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    fip = db.get_floating_ip(floatingip_id, project_id=project_id)
    if not fip:
        raise HTTPException(status_code=404, detail="Floating IP not found")
    return {"floatingip": fip.to_dict()}


@router.put("/v2.0/floatingips/{floatingip_id}")
async def update_floating_ip(
    floatingip_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a floating IP (associate/disassociate).

    Only allows updating floating IPs owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("floatingip", {})
    fip = db.update_floating_ip(
        floatingip_id=floatingip_id,
        project_id=project_id,
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
    """Delete a floating IP.

    Only allows deleting floating IPs owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_floating_ip(floatingip_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Floating IP not found")
    return Response(status_code=204)


# Security Groups
@router.get("/v2.0/security-groups")
async def list_security_groups(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    name: str | None = Query(None),
) -> dict[str, Any]:
    """List security groups.

    Ensures the default security group exists for the tenant before listing.
    """
    project_id = _get_project_id(x_auth_token)
    # Ensure default security group exists for this tenant
    db.get_or_create_default_security_group(project_id)
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
    """Get security group details.

    Only returns security groups owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    sg = db.get_security_group(security_group_id, project_id=project_id)
    if not sg:
        raise HTTPException(status_code=404, detail="Security group not found")
    return {"security_group": sg.to_dict()}


@router.put("/v2.0/security-groups/{security_group_id}")
async def update_security_group(
    security_group_id: str,
    request: dict[str, Any],
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a security group.

    Only allows updating security groups owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    data = request.get("security_group", {})
    sg = db.update_security_group(
        security_group_id=security_group_id,
        project_id=project_id,
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
    """Delete a security group.

    Only allows deleting security groups owned by the requesting tenant.
    Cannot delete the default security group.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_security_group(security_group_id, project_id=project_id)
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
    """Get security group rule details.

    Only returns rules owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    rule = db.get_security_group_rule(rule_id, project_id=project_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Security group rule not found")
    return {"security_group_rule": rule.to_dict()}


@router.delete("/v2.0/security-group-rules/{rule_id}", status_code=204, response_model=None)
async def delete_security_group_rule(
    rule_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a security group rule.

    Only allows deleting rules owned by the requesting tenant.
    """
    project_id = _get_project_id(x_auth_token)
    success = db.delete_security_group_rule(rule_id, project_id=project_id)
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
@router.get("/v2.0/quotas/{project_id}/details.json")
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


# ==================== RBAC Policies ====================


class RbacPolicyRequest(BaseModel):
    """Request model for creating an RBAC policy."""

    model_config = ConfigDict(populate_by_name=True)

    object_type: str
    object_id: str
    target_tenant: str = Field(alias="target_tenant")
    action: str = "access_as_shared"


class RbacPolicyUpdateRequest(BaseModel):
    """Request model for updating an RBAC policy."""

    model_config = ConfigDict(populate_by_name=True)

    target_tenant: str = Field(alias="target_tenant")


@router.get("/v2.0/rbac-policies")
async def list_rbac_policies(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    object_type: str | None = Query(None),
    object_id: str | None = Query(None),
    target_tenant: str | None = Query(None),
    action: str | None = Query(None),
) -> dict[str, Any]:
    """List RBAC policies."""
    policies = db.list_rbac_policies(
        object_type=object_type,
        object_id=object_id,
        target_project=target_tenant,
        action=action,
    )
    return {"rbac_policies": [p.to_dict() for p in policies]}


@router.post("/v2.0/rbac-policies", status_code=201)
async def create_rbac_policy(
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create an RBAC policy."""
    body = await request.json()
    policy_data = body.get("rbac_policy", {})

    # Validate required fields
    object_type = policy_data.get("object_type")
    object_id = policy_data.get("object_id")
    target_tenant = policy_data.get("target_tenant")
    action = policy_data.get("action", "access_as_shared")

    if not object_type or not object_id or not target_tenant:
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Validate object_type
    valid_types = [
        "network",
        "qos_policy",
        "security_group",
        "address_scope",
        "subnetpool",
        "address_group",
    ]
    if object_type not in valid_types:
        raise HTTPException(
            status_code=400, detail=f"Invalid object_type. Must be one of: {valid_types}"
        )

    # Validate action
    valid_actions = ["access_as_shared", "access_as_external"]
    if action not in valid_actions:
        raise HTTPException(
            status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}"
        )

    # Get project_id from token or use default
    project_id = "admin"
    if x_auth_token:
        try:
            token = validate_token_simple(x_auth_token, "Neutron")
            project_id = token.project_id
        except HTTPException:
            project_id = "admin"  # Fallback for development

    policy = db.create_rbac_policy(
        object_type=object_type,
        object_id=object_id,
        target_project=target_tenant,
        project_id=project_id,
        action=action,
    )

    return {"rbac_policy": policy.to_dict()}


@router.get("/v2.0/rbac-policies/{policy_id}")
async def get_rbac_policy(
    policy_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get an RBAC policy by ID."""
    policy = db.get_rbac_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="RBAC policy not found")
    return {"rbac_policy": policy.to_dict()}


@router.put("/v2.0/rbac-policies/{policy_id}")
async def update_rbac_policy(
    policy_id: str,
    request: Request,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update an RBAC policy (only target_tenant can be updated)."""
    body = await request.json()
    policy_data = body.get("rbac_policy", {})

    target_tenant = policy_data.get("target_tenant")

    policy = db.update_rbac_policy(
        policy_id=policy_id,
        target_project=target_tenant,
    )

    if not policy:
        raise HTTPException(status_code=404, detail="RBAC policy not found")

    return {"rbac_policy": policy.to_dict()}


@router.delete("/v2.0/rbac-policies/{policy_id}", status_code=204, response_model=None)
async def delete_rbac_policy(
    policy_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete an RBAC policy."""
    success = db.delete_rbac_policy(policy_id)
    if not success:
        raise HTTPException(status_code=404, detail="RBAC policy not found")
    return Response(status_code=204)


# Replaced by dynamic extensions endpoint below


# Extensions endpoints


@router.get("/v2.0/extensions")
async def list_neutron_extensions(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List all available Neutron extensions."""
    _get_project_id(x_auth_token)  # Validate token

    extensions = db.list_neutron_extensions()
    return {"extensions": [ext.to_dict() for ext in extensions]}


@router.get("/v2.0/extensions/{extension_alias}")
async def get_neutron_extension(
    extension_alias: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get details for a specific extension."""
    _get_project_id(x_auth_token)  # Validate token

    extension = db.get_neutron_extension(extension_alias)
    if not extension:
        raise HTTPException(status_code=404, detail=f"Extension {extension_alias} not found")

    return {"extension": extension.to_dict()}


# QoS Policies


class QosPolicyRequest(BaseModel):
    """QoS policy request."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    shared: bool = False
    is_default: bool = False


class QosPolicyBody(BaseModel):
    """Wrapper for QoS policy request."""

    policy: QosPolicyRequest


@router.get("/v2.0/qos/policies")
async def list_qos_policies(
    name: str | None = Query(None),
    shared: bool | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List QoS policies."""
    project_id = _get_project_id(x_auth_token)

    policies = db.list_qos_policies(
        project_id=project_id,
        name=name,
        shared=shared,
    )
    return {"policies": [policy.to_dict() for policy in policies]}


@router.post("/v2.0/qos/policies", status_code=201)
async def create_qos_policy(
    body: QosPolicyBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a QoS policy."""
    project_id = _get_project_id(x_auth_token)

    policy = db.create_qos_policy(
        name=body.policy.name,
        description=body.policy.description,
        shared=body.policy.shared,
        project_id=project_id,
        is_default=body.policy.is_default,
    )

    return {"policy": policy.to_dict()}


@router.get("/v2.0/qos/policies/{policy_id}")
async def get_qos_policy(
    policy_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a QoS policy by ID."""
    project_id = _get_project_id(x_auth_token)

    policy = db.get_qos_policy(policy_id, project_id=project_id)
    if not policy:
        raise HTTPException(status_code=404, detail="QoS policy not found")

    return {"policy": policy.to_dict()}


@router.put("/v2.0/qos/policies/{policy_id}")
async def update_qos_policy(
    policy_id: str,
    body: QosPolicyBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a QoS policy."""
    project_id = _get_project_id(x_auth_token)

    policy = db.update_qos_policy(
        policy_id=policy_id,
        project_id=project_id,
        name=body.policy.name,
        description=body.policy.description,
        shared=body.policy.shared,
    )
    if not policy:
        raise HTTPException(status_code=404, detail="QoS policy not found")

    return {"policy": policy.to_dict()}


@router.delete("/v2.0/qos/policies/{policy_id}", status_code=204)
async def delete_qos_policy(
    policy_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a QoS policy."""
    project_id = _get_project_id(x_auth_token)

    success = db.delete_qos_policy(policy_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="QoS policy not found")

    return Response(status_code=204)


@router.get("/v2.0/qos/rule-types")
async def list_qos_rule_types(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List available QoS rule types."""
    _get_project_id(x_auth_token)  # Validate token

    rule_types = db.list_qos_rule_types()
    return {"rule_types": [rt.to_dict() for rt in rule_types]}


# Agent Management


class AgentRequest(BaseModel):
    """Agent update request."""

    admin_state_up: bool | None = None
    description: str | None = None


class AgentBody(BaseModel):
    """Wrapper for agent request."""

    agent: AgentRequest


@router.get("/v2.0/agents")
async def list_agents(
    agent_type: str | None = Query(None),
    host: str | None = Query(None),
    alive: bool | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List Neutron agents."""
    _get_project_id(x_auth_token)  # Validate token

    agents = db.list_neutron_agents(
        agent_type=agent_type,
        host=host,
        alive=alive,
    )
    return {"agents": [agent.to_dict() for agent in agents]}


@router.get("/v2.0/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a Neutron agent by ID."""
    _get_project_id(x_auth_token)  # Validate token

    agent = db.get_neutron_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"agent": agent.to_dict()}


@router.put("/v2.0/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a Neutron agent."""
    _get_project_id(x_auth_token)  # Validate token

    agent = db.update_neutron_agent(
        agent_id=agent_id,
        admin_state_up=body.agent.admin_state_up,
        description=body.agent.description,
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"agent": agent.to_dict()}


@router.delete("/v2.0/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a Neutron agent."""
    _get_project_id(x_auth_token)  # Validate token

    success = db.delete_neutron_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

    return Response(status_code=204)


# Trunk Networking


class TrunkRequest(BaseModel):
    """Trunk request."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    port_id: str
    description: str = ""
    admin_state_up: bool = True
    sub_ports: list[dict[str, Any]] = Field(default_factory=list)


class TrunkBody(BaseModel):
    """Wrapper for trunk request."""

    trunk: TrunkRequest


class TrunkSubPortsBody(BaseModel):
    """Sub-ports modification request."""

    sub_ports: list[dict[str, Any]]


@router.get("/v2.0/trunks")
async def list_trunks(
    name: str | None = Query(None),
    port_id: str | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List trunks."""
    project_id = _get_project_id(x_auth_token)

    trunks = db.list_trunks(
        project_id=project_id,
        name=name,
        port_id=port_id,
    )
    return {"trunks": [trunk.to_dict() for trunk in trunks]}


@router.post("/v2.0/trunks", status_code=201)
async def create_trunk(
    body: TrunkBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a trunk."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.create_trunk(
        name=body.trunk.name,
        port_id=body.trunk.port_id,
        description=body.trunk.description,
        admin_state_up=body.trunk.admin_state_up,
        project_id=project_id,
        sub_ports=body.trunk.sub_ports,
    )

    return {"trunk": trunk.to_dict()}


@router.get("/v2.0/trunks/{trunk_id}")
async def get_trunk(
    trunk_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a trunk by ID."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.get_trunk(trunk_id, project_id=project_id)
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return {"trunk": trunk.to_dict()}


@router.put("/v2.0/trunks/{trunk_id}")
async def update_trunk(
    trunk_id: str,
    body: TrunkBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a trunk."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.update_trunk(
        trunk_id=trunk_id,
        project_id=project_id,
        name=body.trunk.name,
        description=body.trunk.description,
        admin_state_up=body.trunk.admin_state_up,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return {"trunk": trunk.to_dict()}


@router.delete("/v2.0/trunks/{trunk_id}", status_code=204)
async def delete_trunk(
    trunk_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a trunk."""
    project_id = _get_project_id(x_auth_token)

    success = db.delete_trunk(trunk_id, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return Response(status_code=204)


@router.put("/v2.0/trunks/{trunk_id}/add_subports", status_code=200)
async def add_subports_to_trunk(
    trunk_id: str,
    body: TrunkSubPortsBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Add sub-ports to a trunk."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.add_subports_to_trunk(
        trunk_id=trunk_id,
        sub_ports=body.sub_ports,
        project_id=project_id,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return {"trunk": trunk.to_dict()}


@router.put("/v2.0/trunks/{trunk_id}/remove_subports", status_code=200)
async def remove_subports_from_trunk(
    trunk_id: str,
    body: TrunkSubPortsBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Remove sub-ports from a trunk."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.remove_subports_from_trunk(
        trunk_id=trunk_id,
        sub_ports=body.sub_ports,
        project_id=project_id,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return {"trunk": trunk.to_dict()}


@router.get("/v2.0/trunks/{trunk_id}/get_subports")
async def get_trunk_subports(
    trunk_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get sub-ports of a trunk."""
    project_id = _get_project_id(x_auth_token)

    trunk = db.get_trunk(trunk_id, project_id=project_id)
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    return {"sub_ports": [sp.to_dict() for sp in trunk.sub_ports]}


# Service Flavors (useful for application developers)


class NeutronFlavorRequest(BaseModel):
    """Neutron service flavor request."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    service_type: str
    enabled: bool = True


class NeutronFlavorBody(BaseModel):
    """Wrapper for Neutron flavor request."""

    flavor: NeutronFlavorRequest


@router.get("/v2.0/flavors")
async def list_neutron_flavors(
    service_type: str | None = Query(None),
    enabled: bool | None = Query(None),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List Neutron service flavors."""
    _get_project_id(x_auth_token)  # Validate token

    flavors = db.list_neutron_flavors(service_type=service_type, enabled=enabled)
    return {"flavors": [flavor.to_dict() for flavor in flavors]}


@router.post("/v2.0/flavors", status_code=201)
async def create_neutron_flavor(
    body: NeutronFlavorBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Create a Neutron service flavor."""
    _get_project_id(x_auth_token)  # Validate token

    flavor = db.create_neutron_flavor(
        name=body.flavor.name,
        description=body.flavor.description,
        service_type=body.flavor.service_type,
        enabled=body.flavor.enabled,
    )

    return {"flavor": flavor.to_dict()}


@router.get("/v2.0/flavors/{flavor_id}")
async def get_neutron_flavor(
    flavor_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a Neutron service flavor by ID."""
    _get_project_id(x_auth_token)  # Validate token

    flavor = db.get_neutron_flavor(flavor_id)
    if not flavor:
        raise HTTPException(status_code=404, detail="Flavor not found")

    return {"flavor": flavor.to_dict()}


@router.put("/v2.0/flavors/{flavor_id}")
async def update_neutron_flavor(
    flavor_id: str,
    body: NeutronFlavorBody,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Update a Neutron service flavor."""
    _get_project_id(x_auth_token)  # Validate token

    flavor = db.update_neutron_flavor(
        flavor_id=flavor_id,
        name=body.flavor.name,
        description=body.flavor.description,
        enabled=body.flavor.enabled,
    )
    if not flavor:
        raise HTTPException(status_code=404, detail="Flavor not found")

    return {"flavor": flavor.to_dict()}


@router.delete("/v2.0/flavors/{flavor_id}", status_code=204)
async def delete_neutron_flavor(
    flavor_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> Response:
    """Delete a Neutron service flavor."""
    _get_project_id(x_auth_token)  # Validate token

    success = db.delete_neutron_flavor(flavor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Flavor not found")

    return Response(status_code=204)


@router.get("/v2.0/service_profiles")
async def list_service_profiles(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List Neutron service profiles."""
    _get_project_id(x_auth_token)  # Validate token

    profiles = db.list_service_profiles()
    return {"service_profiles": [profile.to_dict() for profile in profiles]}


@router.get("/v2.0/service_profiles/{profile_id}")
async def get_service_profile(
    profile_id: str,
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Get a service profile by ID."""
    _get_project_id(x_auth_token)  # Validate token

    profile = db.get_service_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Service profile not found")

    return {"service_profile": profile.to_dict()}
