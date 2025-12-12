"""Pydantic models for preset validation."""

from pydantic import BaseModel, Field


class SecurityGroupRuleConfig(BaseModel):
    """Configuration for a security group rule."""

    direction: str = "ingress"
    protocol: str | None = None
    port_range_min: int | None = None
    port_range_max: int | None = None
    remote_ip_prefix: str | None = None
    remote_group: str | None = None
    ethertype: str = "IPv4"


class SecurityGroupConfig(BaseModel):
    """Configuration for a security group."""

    name: str
    description: str = ""
    project: str | None = None
    rules: list[SecurityGroupRuleConfig] = Field(default_factory=list)


class SubnetConfig(BaseModel):
    """Configuration for a subnet."""

    name: str
    cidr: str
    gateway: str | None = None
    enable_dhcp: bool = True
    dns_nameservers: list[str] = Field(default_factory=list)
    allocation_pools: list[dict[str, str]] = Field(default_factory=list)


class NetworkConfig(BaseModel):
    """Configuration for a network."""

    name: str
    project: str | None = None
    external: bool = False
    shared: bool = False
    subnets: list[SubnetConfig] = Field(default_factory=list)


class RouterInterfaceConfig(BaseModel):
    """Configuration for a router interface."""

    subnet: str


class RouterConfig(BaseModel):
    """Configuration for a router."""

    name: str
    project: str | None = None
    external_network: str | None = None
    interfaces: list[RouterInterfaceConfig] = Field(default_factory=list)


class FloatingIPConfig(BaseModel):
    """Configuration for a floating IP."""

    project: str | None = None
    floating_network: str
    server: str | None = None
    fixed_ip: str | None = None


class ServerConfig(BaseModel):
    """Configuration for a server."""

    name: str
    project: str | None = None
    flavor: str = "m1.small"
    image: str
    network: str | None = None
    networks: list[str] = Field(default_factory=list)
    security_groups: list[str] = Field(default_factory=list)
    key_name: str | None = None
    availability_zone: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    user_data: str | None = None


class VolumeAttachmentConfig(BaseModel):
    """Configuration for volume attachment."""

    server: str
    device: str | None = None


class VolumeConfig(BaseModel):
    """Configuration for a volume."""

    name: str
    project: str | None = None
    size: int = 10
    volume_type: str | None = None
    description: str = ""
    bootable: bool = False
    attach_to: str | None = None
    device: str | None = None


class SnapshotConfig(BaseModel):
    """Configuration for a volume snapshot."""

    name: str
    volume: str
    project: str | None = None
    description: str = ""


class PoolMemberConfig(BaseModel):
    """Configuration for a load balancer pool member."""

    server: str | None = None
    address: str | None = None
    port: int
    weight: int = 1


class PoolConfig(BaseModel):
    """Configuration for a load balancer pool."""

    name: str
    protocol: str = "HTTP"
    lb_algorithm: str = "ROUND_ROBIN"
    members: list[PoolMemberConfig] = Field(default_factory=list)


class ListenerConfig(BaseModel):
    """Configuration for a load balancer listener."""

    name: str
    protocol: str = "HTTP"
    port: int
    pool: PoolConfig | None = None


class LoadBalancerConfig(BaseModel):
    """Configuration for a load balancer."""

    name: str
    project: str | None = None
    vip_subnet: str
    vip_address: str | None = None
    listeners: list[ListenerConfig] = Field(default_factory=list)


class KeypairConfig(BaseModel):
    """Configuration for a keypair."""

    name: str
    user: str | None = None
    public_key: str | None = None


class ImageConfig(BaseModel):
    """Configuration for a Glance image."""

    name: str
    visibility: str = "public"
    container_format: str = "bare"
    disk_format: str = "qcow2"
    min_disk: int = 0
    min_ram: int = 0
    size: int = 0
    os_distro: str | None = None
    os_version: str | None = None
    architecture: str = "x86_64"


class UserConfig(BaseModel):
    """Configuration for a user."""

    name: str
    password: str = "password"
    email: str | None = None
    roles: list[str] = Field(default_factory=list)


class ProjectConfig(BaseModel):
    """Configuration for a project/tenant."""

    name: str
    description: str = ""
    domain: str = "default"
    users: list[UserConfig] = Field(default_factory=list)


class KeystoneConfig(BaseModel):
    """Configuration for Keystone resources."""

    projects: list[ProjectConfig] = Field(default_factory=list)


class GlanceConfig(BaseModel):
    """Configuration for Glance resources."""

    images: list[ImageConfig] = Field(default_factory=list)


class NeutronConfig(BaseModel):
    """Configuration for Neutron resources."""

    networks: list[NetworkConfig] = Field(default_factory=list)
    routers: list[RouterConfig] = Field(default_factory=list)
    security_groups: list[SecurityGroupConfig] = Field(default_factory=list)
    floating_ips: list[FloatingIPConfig] = Field(default_factory=list)


class NovaConfig(BaseModel):
    """Configuration for Nova resources."""

    keypairs: list[KeypairConfig] = Field(default_factory=list)
    servers: list[ServerConfig] = Field(default_factory=list)


class CinderConfig(BaseModel):
    """Configuration for Cinder resources."""

    volumes: list[VolumeConfig] = Field(default_factory=list)
    snapshots: list[SnapshotConfig] = Field(default_factory=list)


class OctaviaConfig(BaseModel):
    """Configuration for Octavia resources."""

    load_balancers: list[LoadBalancerConfig] = Field(default_factory=list)


class PresetConfig(BaseModel):
    """Root configuration for a preset."""

    name: str
    description: str = ""
    # If true, reset database before loading preset
    reset_first: bool = True
    # Service configurations
    keystone: KeystoneConfig = Field(default_factory=KeystoneConfig)
    glance: GlanceConfig = Field(default_factory=GlanceConfig)
    neutron: NeutronConfig = Field(default_factory=NeutronConfig)
    nova: NovaConfig = Field(default_factory=NovaConfig)
    cinder: CinderConfig = Field(default_factory=CinderConfig)
    octavia: OctaviaConfig = Field(default_factory=OctaviaConfig)
