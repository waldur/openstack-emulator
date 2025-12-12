# Data Models

This document describes the data models used in the OpenStack Emulator.

## Overview

All models are implemented as Python dataclasses in `emulator/core/models.py`. Each model includes a `to_dict()` method that converts to the OpenStack API response format.

## Identity Models (Keystone)

### Domain

Represents an identity domain that contains projects and users.

```python
@dataclass
class Domain:
    id: str                    # UUID
    name: str                  # Unique name
    description: str = ""
    enabled: bool = True
    tags: list[str] = []
```

### Project

Represents a project (tenant) that owns resources.

```python
@dataclass
class Project:
    id: str                    # UUID
    name: str                  # Unique within domain
    description: str = ""
    domain_id: str = "default"
    parent_id: str | None = None  # For hierarchical projects
    enabled: bool = True
    is_domain: bool = False
    tags: list[str] = []
```

### User

Represents an authenticated user.

```python
@dataclass
class User:
    id: str                    # UUID
    name: str                  # Unique within domain
    description: str = ""
    domain_id: str = "default"
    default_project_id: str | None = None
    enabled: bool = True
    password_hash: str = ""    # SHA-256 hash
    email: str = ""
    created_at: datetime
    updated_at: datetime
```

### Role & RoleAssignment

```python
@dataclass
class Role:
    id: str
    name: str                  # admin, member, reader, etc.
    description: str = ""
    domain_id: str | None = None  # Global or domain-scoped

@dataclass
class RoleAssignment:
    role_id: str
    user_id: str | None = None
    group_id: str | None = None
    project_id: str | None = None
    domain_id: str | None = None
    inherited: bool = False
```

### Token

```python
@dataclass
class Token:
    id: str                    # Token value
    user_id: str
    user_name: str
    project_id: str
    project_name: str
    domain_id: str = "default"
    domain_name: str = "Default"
    roles: list[dict[str, str]]  # [{"id": "...", "name": "admin"}]
    issued_at: datetime
    expires_at: datetime | None
    catalog: list[dict[str, Any]]  # Service catalog
```

## Compute Models (Nova)

### Server

Represents a virtual machine instance.

```python
@dataclass
class Server:
    id: str                    # UUID
    name: str
    status: ServerStatus       # ACTIVE, BUILD, SHUTOFF, etc.
    task_state: TaskState | None
    power_state: PowerState    # RUNNING, SHUTDOWN, etc.
    tenant_id: str             # Owning project
    user_id: str               # Creating user
    flavor_id: str             # Reference to Flavor
    image_id: str              # Reference to Image
    host: str = "compute-host-1"
    availability_zone: str = "nova"
    key_name: str | None = None
    created: datetime
    updated: datetime
    launched_at: datetime | None
    terminated_at: datetime | None
    metadata: dict[str, str]
    addresses: dict[str, list[dict]]  # Network -> IPs
    security_groups: list[dict[str, str]]
    admin_pass: str | None
    access_ipv4: str = ""
    access_ipv6: str = ""
    config_drive: str = ""
    progress: int = 0
    fault: dict[str, Any] | None
```

**Status Values:**
- `BUILD` - Server is being created
- `ACTIVE` - Server is running
- `SHUTOFF` - Server is stopped
- `PAUSED` - Server is paused
- `SUSPENDED` - Server is suspended
- `SHELVED` - Server is shelved (offline)
- `ERROR` - Server is in error state
- `DELETED` - Server has been deleted

### Flavor

Represents a VM size/configuration template.

```python
@dataclass
class Flavor:
    id: str
    name: str                  # m1.tiny, m1.small, etc.
    vcpus: int = 1
    ram: int = 512             # MB
    disk: int = 10             # GB
    ephemeral: int = 0         # GB
    swap: int = 0              # MB
    rxtx_factor: float = 1.0
    is_public: bool = True
    disabled: bool = False
    description: str = ""
    extra_specs: dict[str, str]
```

### ServerGroup

For affinity/anti-affinity scheduling.

```python
@dataclass
class ServerGroup:
    id: str
    name: str
    policies: list[str]        # affinity, anti-affinity, soft-*
    members: list[str]         # Server IDs
    project_id: str
    user_id: str
    metadata: dict[str, str]
    created_at: datetime
```

### Keypair

```python
@dataclass
class Keypair:
    name: str                  # Unique per user
    public_key: str
    fingerprint: str
    user_id: str
    type: str = "ssh"
    created_at: datetime
```

## Block Storage Models (Cinder)

### Volume

```python
@dataclass
class Volume:
    id: str
    name: str
    description: str = ""
    status: VolumeStatus       # available, in-use, creating, etc.
    size: int = 1              # GB
    volume_type: str = "lvmdriver-1"
    availability_zone: str = "nova"
    bootable: bool = False
    encrypted: bool = False
    multiattach: bool = False
    source_volid: str | None = None
    snapshot_id: str | None = None
    image_id: str | None = None
    project_id: str
    user_id: str
    host: str | None
    attachments: list[VolumeAttachment]
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime
```

**Status Values:**
- `creating` - Volume is being created
- `available` - Volume is ready for use
- `attaching` - Volume is being attached
- `in-use` - Volume is attached to instance
- `detaching` - Volume is being detached
- `deleting` - Volume is being deleted
- `error` - Volume is in error state

### Snapshot

```python
@dataclass
class Snapshot:
    id: str
    name: str
    description: str = ""
    status: SnapshotStatus
    volume_id: str
    size: int = 0              # GB (inherited from volume)
    project_id: str
    user_id: str
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime
    progress: str = "0%"
```

## Image Models (Glance)

### GlanceImage

```python
@dataclass
class GlanceImage:
    id: str
    name: str
    status: ImageStatus        # queued, saving, active, etc.
    visibility: ImageVisibility  # public, private, shared, community
    protected: bool = False
    owner: str = ""            # project_id
    min_disk: int = 0          # GB
    min_ram: int = 0           # MB
    size: int | None = None    # bytes
    virtual_size: int | None = None
    checksum: str | None = None
    os_hash_algo: str | None = None
    os_hash_value: str | None = None
    os_hidden: bool = False
    container_format: ContainerFormat | None  # bare, ovf, ova, etc.
    disk_format: DiskFormat | None  # qcow2, raw, vmdk, etc.
    created_at: datetime
    updated_at: datetime
    tags: list[str]
    properties: dict[str, Any]  # Custom metadata
    # OS info
    architecture: str | None
    os_distro: str | None
    os_version: str | None
```

### ImageMember

For image sharing between projects.

```python
@dataclass
class ImageMember:
    image_id: str
    member_id: str             # project_id
    status: str = "pending"    # pending, accepted, rejected
    created_at: datetime
    updated_at: datetime
```

## Network Models (Neutron)

### Network

```python
@dataclass
class Network:
    id: str
    name: str
    description: str = ""
    status: NetworkStatus      # ACTIVE, DOWN, BUILD, ERROR
    admin_state_up: bool = True
    shared: bool = False       # Visible to all projects
    external: bool = False     # router:external
    project_id: str
    mtu: int = 1500
    port_security_enabled: bool = True
    provider_network_type: str | None  # flat, vlan, vxlan
    provider_physical_network: str | None
    provider_segmentation_id: int | None
    availability_zones: list[str]
    dns_domain: str = ""
    subnets: list[str]         # Subnet IDs
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### Subnet

```python
@dataclass
class Subnet:
    id: str
    name: str
    description: str = ""
    network_id: str
    ip_version: int = 4        # 4 or 6
    cidr: str                  # e.g., "10.0.0.0/24"
    gateway_ip: str | None
    allocation_pools: list[AllocationPool]
    dns_nameservers: list[str]
    host_routes: list[dict[str, str]]
    enable_dhcp: bool = True
    project_id: str
    ipv6_ra_mode: str | None
    ipv6_address_mode: str | None
    subnetpool_id: str | None
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### Port

```python
@dataclass
class Port:
    id: str
    name: str
    description: str = ""
    network_id: str
    status: PortStatus         # ACTIVE, DOWN, BUILD, ERROR
    admin_state_up: bool = True
    mac_address: str           # fa:16:3e:xx:xx:xx
    fixed_ips: list[FixedIP]   # [{subnet_id, ip_address}]
    device_id: str = ""        # Server ID if attached
    device_owner: str = ""     # compute:nova, network:router_interface
    project_id: str
    security_groups: list[str]  # Security group IDs
    port_security_enabled: bool = True
    allowed_address_pairs: list[dict[str, str]]
    binding_host_id: str = ""
    binding_vnic_type: str = "normal"
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### Router

```python
@dataclass
class Router:
    id: str
    name: str
    description: str = ""
    status: RouterStatus       # ACTIVE, ALLOCATING, ERROR
    admin_state_up: bool = True
    project_id: str
    external_gateway_info: ExternalGatewayInfo | None
    routes: list[dict[str, str]]  # Static routes
    ha: bool = False
    distributed: bool = False
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### SecurityGroup & SecurityGroupRule

```python
@dataclass
class SecurityGroup:
    id: str
    name: str
    description: str = ""
    project_id: str
    security_group_rules: list[SecurityGroupRule]
    stateful: bool = True
    created_at: datetime
    updated_at: datetime
    tags: list[str]

@dataclass
class SecurityGroupRule:
    id: str
    security_group_id: str
    direction: str = "ingress"  # ingress or egress
    ethertype: str = "IPv4"     # IPv4 or IPv6
    protocol: str | None        # tcp, udp, icmp, etc.
    port_range_min: int | None
    port_range_max: int | None
    remote_ip_prefix: str | None  # CIDR
    remote_group_id: str | None
    description: str = ""
    project_id: str
    created_at: datetime
    updated_at: datetime
```

### FloatingIP

```python
@dataclass
class FloatingIP:
    id: str
    description: str = ""
    status: FloatingIPStatus   # ACTIVE, DOWN, ERROR
    floating_network_id: str   # External network
    floating_ip_address: str   # Public IP
    fixed_ip_address: str | None  # Internal IP
    port_id: str | None        # Associated port
    router_id: str | None      # Associated router
    project_id: str
    dns_domain: str = ""
    dns_name: str = ""
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

## Load Balancer Models (Octavia)

### LoadBalancer

```python
@dataclass
class LoadBalancer:
    id: str
    name: str
    description: str = ""
    admin_state_up: bool = True
    vip_subnet_id: str | None
    vip_network_id: str | None
    vip_port_id: str | None
    vip_address: str = ""
    flavor_id: str | None
    availability_zone: str | None
    provider: str = "amphora"
    project_id: str
    provisioning_status: LoadBalancerProvisioningStatus
    operating_status: LoadBalancerOperatingStatus
    listeners: list[Listener]
    pools: list[Pool]
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### Listener

```python
@dataclass
class Listener:
    id: str
    name: str
    description: str = ""
    protocol: ListenerProtocol  # HTTP, HTTPS, TCP, UDP
    protocol_port: int = 80
    connection_limit: int = -1  # -1 = unlimited
    default_pool_id: str | None
    admin_state_up: bool = True
    loadbalancer_id: str
    project_id: str
    provisioning_status: LoadBalancerProvisioningStatus
    operating_status: LoadBalancerOperatingStatus
    default_tls_container_ref: str | None
    l7policies: list[L7Policy]
    created_at: datetime
    updated_at: datetime
    tags: list[str]
```

### Pool & PoolMember

```python
@dataclass
class Pool:
    id: str
    name: str
    description: str = ""
    protocol: PoolProtocol     # HTTP, HTTPS, TCP, etc.
    lb_algorithm: PoolLBAlgorithm  # ROUND_ROBIN, LEAST_CONNECTIONS, etc.
    admin_state_up: bool = True
    loadbalancer_id: str | None
    listener_id: str | None
    healthmonitor_id: str | None
    project_id: str
    provisioning_status: LoadBalancerProvisioningStatus
    operating_status: LoadBalancerOperatingStatus
    members: list[PoolMember]
    session_persistence: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

@dataclass
class PoolMember:
    id: str
    name: str = ""
    address: str = ""          # Backend server IP
    protocol_port: int = 80
    weight: int = 1
    subnet_id: str | None
    admin_state_up: bool = True
    pool_id: str
    project_id: str
    provisioning_status: LoadBalancerProvisioningStatus
    operating_status: LoadBalancerOperatingStatus
    backup: bool = False
    created_at: datetime
    updated_at: datetime
```

### HealthMonitor

```python
@dataclass
class HealthMonitor:
    id: str
    name: str = ""
    type: HealthMonitorType    # HTTP, HTTPS, TCP, PING
    delay: int = 5             # Seconds between checks
    timeout: int = 5           # Seconds to wait for response
    max_retries: int = 3
    max_retries_down: int = 3
    http_method: str = "GET"
    url_path: str = "/"
    expected_codes: str = "200"
    admin_state_up: bool = True
    pool_id: str
    project_id: str
    provisioning_status: LoadBalancerProvisioningStatus
    operating_status: LoadBalancerOperatingStatus
    created_at: datetime
    updated_at: datetime
```

## Quota Models

```python
@dataclass
class NovaQuota:
    project_id: str
    instances: int = 10
    cores: int = 20
    ram: int = 51200           # MB
    metadata_items: int = 128
    injected_files: int = 5
    key_pairs: int = 100
    server_groups: int = 10
    server_group_members: int = 10

@dataclass
class NeutronQuota:
    project_id: str
    network: int = 100
    subnet: int = 100
    port: int = 500
    router: int = 10
    floatingip: int = 50
    security_group: int = 10
    security_group_rule: int = 100

@dataclass
class CinderQuota:
    project_id: str
    volumes: int = 10
    snapshots: int = 10
    gigabytes: int = 1000      # GB
    per_volume_gigabytes: int = -1  # -1 = unlimited
    backups: int = 10
    backup_gigabytes: int = 1000
```

## Related Documentation

- [Tenant Isolation](./tenant-isolation.md) - How resources are isolated
- [Architecture Overview](./README.md) - System architecture
