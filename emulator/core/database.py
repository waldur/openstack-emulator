"""In-memory database for OpenStack emulator."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from emulator.core.models import (
    AllocationPool,
    CinderQuota,
    ContainerFormat,
    Credential,
    DiskFormat,
    Domain,
    Endpoint,
    ExternalGatewayInfo,
    FixedIP,
    Flavor,
    FloatingIP,
    FloatingIPStatus,
    GlanceImage,
    Group,
    HealthMonitor,
    HealthMonitorType,
    Image,
    ImageMember,
    ImageStatus,
    ImageVisibility,
    Keypair,
    L7Policy,
    L7PolicyAction,
    L7Rule,
    L7RuleCompareType,
    L7RuleType,
    Listener,
    ListenerProtocol,
    LoadBalancer,
    LoadBalancerOperatingStatus,
    LoadBalancerProvisioningStatus,
    Network,
    NeutronQuota,
    NovaQuota,
    Pool,
    PoolLBAlgorithm,
    PoolMember,
    PoolProtocol,
    Port,
    PowerState,
    Project,
    QosSpec,
    RbacPolicy,
    Region,
    Role,
    RoleAssignment,
    Router,
    SecurityGroup,
    SecurityGroupRule,
    Server,
    ServerGroup,
    ServerStatus,
    Service,
    Snapshot,
    SnapshotStatus,
    Subnet,
    Token,
    User,
    Volume,
    VolumeAttachment,
    VolumeStatus,
    VolumeType,
)


class Database:
    """In-memory database for storing OpenStack resources."""

    def __init__(self, persist_path: str | None = None) -> None:
        """Initialize the database with optional persistence."""
        self._lock = threading.RLock()
        self.persist_path = persist_path

        # Storage dictionaries - Nova
        self._servers: dict[str, Server] = {}
        self._flavors: dict[str, Flavor] = {}
        self._images: dict[str, Image] = {}
        self._keypairs: dict[str, Keypair] = {}  # key: user_id:name
        self._tokens: dict[str, Token] = {}

        # Storage dictionaries - Keystone
        self._domains: dict[str, Domain] = {}
        self._projects: dict[str, Project] = {}
        self._users: dict[str, User] = {}
        self._roles: dict[str, Role] = {}
        self._role_assignments: list[RoleAssignment] = []
        self._groups: dict[str, Group] = {}
        self._group_memberships: dict[str, set[str]] = {}  # group_id -> set of user_ids
        self._services: dict[str, Service] = {}
        self._endpoints: dict[str, Endpoint] = {}
        self._regions: dict[str, Region] = {}
        self._credentials: dict[str, Credential] = {}

        # Storage dictionaries - Cinder
        self._volumes: dict[str, Volume] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._volume_types: dict[str, VolumeType] = {}
        self._qos_specs: dict[str, QosSpec] = {}

        # Storage dictionaries - Glance
        self._glance_images: dict[str, GlanceImage] = {}
        self._image_members: dict[str, list[ImageMember]] = {}  # image_id -> list of members

        # Storage dictionaries - Neutron
        self._networks: dict[str, Network] = {}
        self._subnets: dict[str, Subnet] = {}
        self._ports: dict[str, Port] = {}
        self._routers: dict[str, Router] = {}
        self._floating_ips: dict[str, FloatingIP] = {}
        self._security_groups: dict[str, SecurityGroup] = {}
        self._security_group_rules: dict[str, SecurityGroupRule] = {}
        self._next_floating_ip: int = 1  # For generating sequential floating IPs

        # Storage dictionaries - Nova Server Groups
        self._server_groups: dict[str, ServerGroup] = {}

        # Storage dictionaries - Quotas
        self._nova_quotas: dict[str, NovaQuota] = {}
        self._neutron_quotas: dict[str, NeutronQuota] = {}
        self._cinder_quotas: dict[str, CinderQuota] = {}

        # Storage dictionaries - RBAC Policies
        self._rbac_policies: dict[str, RbacPolicy] = {}

        # Storage dictionaries - Octavia
        self._load_balancers: dict[str, LoadBalancer] = {}
        self._listeners: dict[str, Listener] = {}
        self._pools: dict[str, Pool] = {}
        self._pool_members: dict[str, PoolMember] = {}  # key: pool_id:member_id
        self._health_monitors: dict[str, HealthMonitor] = {}
        self._l7policies: dict[str, L7Policy] = {}
        self._l7rules: dict[str, L7Rule] = {}  # key: policy_id:rule_id
        self._next_lb_vip: int = 1  # For generating sequential VIP addresses

        # Initialize with default data
        self._init_default_flavors()
        self._init_default_images()
        self._init_default_glance_images()
        self._init_default_keystone_data()
        self._init_default_volume_types()
        self._init_default_neutron_data()

    def _init_default_flavors(self) -> None:
        """Create default flavors matching standard OpenStack flavors."""
        default_flavors = [
            Flavor(id="1", name="m1.tiny", vcpus=1, ram=512, disk=1),
            Flavor(id="2", name="m1.small", vcpus=1, ram=2048, disk=20),
            Flavor(id="3", name="m1.medium", vcpus=2, ram=4096, disk=40),
            Flavor(id="4", name="m1.large", vcpus=4, ram=8192, disk=80),
            Flavor(id="5", name="m1.xlarge", vcpus=8, ram=16384, disk=160),
        ]
        for flavor in default_flavors:
            self._flavors[flavor.id] = flavor

    def _init_default_images(self) -> None:
        """Create default images for testing (Nova-compatible)."""
        # These will be populated from Glance images
        pass

    def _init_default_glance_images(self) -> None:
        """Create default Glance images for testing."""
        default_images = [
            GlanceImage(
                id=str(uuid4()),
                name="cirros-0.6.2-x86_64",
                status=ImageStatus.ACTIVE,
                visibility=ImageVisibility.PUBLIC,
                owner="admin",
                min_disk=1,
                min_ram=128,
                size=21430272,
                container_format=ContainerFormat.BARE,
                disk_format=DiskFormat.QCOW2,
                checksum="b40b105be95580a32679a71d0f44e325",
                os_hash_algo="sha512",
                os_hash_value="6b813aa46bb90b4da216a4d19376593fa3f4fc7e617f03a92b7fe11e9a3981cbe8f0959dbebe36225e5f53dc4492341a4863cac4ed1ee0909f3fc78ef9c3e869",
                architecture="x86_64",
                os_distro="cirros",
                os_version="0.6.2",
            ),
            GlanceImage(
                id=str(uuid4()),
                name="ubuntu-22.04-server",
                status=ImageStatus.ACTIVE,
                visibility=ImageVisibility.PUBLIC,
                owner="admin",
                min_disk=8,
                min_ram=512,
                size=2361393152,
                container_format=ContainerFormat.BARE,
                disk_format=DiskFormat.QCOW2,
                checksum="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                architecture="x86_64",
                os_distro="ubuntu",
                os_version="22.04",
            ),
            GlanceImage(
                id=str(uuid4()),
                name="debian-12-genericcloud",
                status=ImageStatus.ACTIVE,
                visibility=ImageVisibility.PUBLIC,
                owner="admin",
                min_disk=2,
                min_ram=512,
                size=261816320,
                container_format=ContainerFormat.BARE,
                disk_format=DiskFormat.QCOW2,
                checksum="d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9",
                architecture="x86_64",
                os_distro="debian",
                os_version="12",
            ),
        ]
        for image in default_images:
            self._glance_images[image.id] = image
            # Also populate Nova-compatible images
            self._images[image.id] = image.to_nova_image()

    def _init_default_keystone_data(self) -> None:
        """Initialize default Keystone resources (domain, project, user, roles, services)."""
        # Create default domain
        self._default_domain = Domain(
            id="default",
            name="Default",
            description="The default domain",
            enabled=True,
        )
        self._domains["default"] = self._default_domain

        # Create admin project
        self._default_project_id = str(uuid4())
        self._default_project_name = "admin"
        admin_project = Project(
            id=self._default_project_id,
            name=self._default_project_name,
            description="Bootstrap project for initial admin user",
            domain_id="default",
            enabled=True,
        )
        self._projects[admin_project.id] = admin_project

        # Create service project
        service_project_id = str(uuid4())
        service_project = Project(
            id=service_project_id,
            name="service",
            description="Service project",
            domain_id="default",
            enabled=True,
        )
        self._projects[service_project.id] = service_project

        # Create admin user
        self._default_user_id = str(uuid4())
        self._default_user_name = "admin"
        admin_user = User(
            id=self._default_user_id,
            name=self._default_user_name,
            description="Admin user",
            domain_id="default",
            default_project_id=self._default_project_id,
            enabled=True,
            email="admin@example.com",
        )
        self._users[admin_user.id] = admin_user

        # Create default roles
        admin_role = Role(id=str(uuid4()), name="admin", description="Admin role")
        member_role = Role(id=str(uuid4()), name="member", description="Member role")
        reader_role = Role(id=str(uuid4()), name="reader", description="Reader role")
        self._roles[admin_role.id] = admin_role
        self._roles[member_role.id] = member_role
        self._roles[reader_role.id] = reader_role
        self._admin_role_id = admin_role.id

        # Assign admin role to admin user on admin project
        self._role_assignments.append(
            RoleAssignment(
                role_id=admin_role.id,
                user_id=admin_user.id,
                project_id=admin_project.id,
            )
        )

        # Create default region
        default_region = Region(
            id="RegionOne",
            description="Default region",
        )
        self._regions["RegionOne"] = default_region

        # Create default services and endpoints (will be populated dynamically)
        self._init_default_services()

    def _init_default_services(self) -> None:
        """Initialize default OpenStack services."""
        # Identity service (Keystone)
        identity_service = Service(
            id=str(uuid4()),
            name="keystone",
            type="identity",
            description="OpenStack Identity Service",
            enabled=True,
        )
        self._services[identity_service.id] = identity_service

        # Compute service (Nova)
        compute_service = Service(
            id=str(uuid4()),
            name="nova",
            type="compute",
            description="OpenStack Compute Service",
            enabled=True,
        )
        self._services[compute_service.id] = compute_service

        # Image service (Glance)
        image_service = Service(
            id=str(uuid4()),
            name="glance",
            type="image",
            description="OpenStack Image Service",
            enabled=True,
        )
        self._services[image_service.id] = image_service

        # Block Storage service (Cinder)
        volume_service = Service(
            id=str(uuid4()),
            name="cinder",
            type="volumev3",
            description="OpenStack Block Storage Service",
            enabled=True,
        )
        self._services[volume_service.id] = volume_service

        # Store service IDs for catalog generation
        self._service_ids = {
            "identity": identity_service.id,
            "compute": compute_service.id,
            "image": image_service.id,
            "volumev3": volume_service.id,
        }

    def _init_default_volume_types(self) -> None:
        """Create default volume types."""
        default_types = [
            VolumeType(
                id=str(uuid4()),
                name="lvmdriver-1",
                description="Default LVM volume type",
                is_public=True,
            ),
            VolumeType(
                id=str(uuid4()),
                name="__DEFAULT__",
                description="Default volume type",
                is_public=True,
            ),
        ]
        for vtype in default_types:
            self._volume_types[vtype.id] = vtype

    # Token operations
    def create_token(
        self,
        user_name: str = "admin",
        project_name: str = "admin",
        base_url: str = "http://localhost:8774",
        domain_id: str = "default",
    ) -> Token:
        """Create a new authentication token."""
        with self._lock:
            # Find user by name and domain
            user = self.get_user_by_name(user_name, domain_id)
            if not user:
                # Create a temporary user record for testing
                user = User(
                    id=self._default_user_id,
                    name=user_name,
                    domain_id=domain_id,
                )

            # Find project by name and domain
            project = self.get_project_by_name(project_name, domain_id)
            if not project:
                # Use default project
                project = Project(
                    id=self._default_project_id,
                    name=project_name,
                    domain_id=domain_id,
                )

            # Get user's roles on this project
            roles = self.get_user_roles_on_project(user.id, project.id)
            if not roles:
                # Default to admin role for testing
                roles = [{"id": self._admin_role_id, "name": "admin"}]

            # Get domain info
            domain = self._domains.get(domain_id, self._default_domain)

            token = Token(
                id=str(uuid4()),
                user_id=user.id,
                user_name=user.name,
                project_id=project.id,
                project_name=project.name,
                domain_id=domain.id,
                domain_name=domain.name,
                roles=roles,
                issued_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24),
                catalog=self._generate_service_catalog(base_url),
            )
            self._tokens[token.id] = token
            return token

    def validate_token(self, token_id: str) -> Token | None:
        """Validate and return a token if valid."""
        with self._lock:
            token = self._tokens.get(token_id)
            if token and token.expires_at and token.expires_at > datetime.utcnow():
                return token
            return None

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token."""
        with self._lock:
            if token_id in self._tokens:
                del self._tokens[token_id]
                return True
            return False

    def _generate_service_catalog(self, base_url: str) -> list[dict[str, Any]]:
        """Generate a service catalog for tokens.

        Uses standard OpenStack ports:
        - Keystone (Identity): 5000
        - Nova (Compute): 8774
        - Cinder (Block Storage): 8776
        - Glance (Image): 9292
        - Neutron (Network): 9696
        """
        from urllib.parse import urlparse

        # Parse the base URL to extract host for building service URLs
        parsed = urlparse(base_url)
        host = parsed.hostname or "localhost"
        scheme = parsed.scheme or "http"

        # Build URLs with standard OpenStack ports
        keystone_url = f"{scheme}://{host}:5000"
        nova_url = f"{scheme}://{host}:8774"
        cinder_url = f"{scheme}://{host}:8776"
        glance_url = f"{scheme}://{host}:9292"
        neutron_url = f"{scheme}://{host}:9696"

        return [
            {
                "type": "compute",
                "name": "nova",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{nova_url}/v2.1",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{nova_url}/v2.1",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{nova_url}/v2.1",
                    },
                ],
            },
            {
                "type": "identity",
                "name": "keystone",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{keystone_url}/v3",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{keystone_url}/v3",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{keystone_url}/v3",
                    },
                ],
            },
            {
                "type": "image",
                "name": "glance",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{glance_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{glance_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{glance_url}",
                    },
                ],
            },
            {
                "type": "volumev3",
                "name": "cinderv3",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{cinder_url}/v3/%(project_id)s",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{cinder_url}/v3/%(project_id)s",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{cinder_url}/v3/%(project_id)s",
                    },
                ],
            },
            {
                "type": "network",
                "name": "neutron",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{neutron_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{neutron_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{neutron_url}",
                    },
                ],
            },
        ]

    # Server operations
    def create_server(
        self,
        name: str,
        flavor_id: str,
        image_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        key_name: str | None = None,
        metadata: dict[str, str] | None = None,
        security_groups: list[dict[str, str]] | None = None,
        availability_zone: str = "nova",
        networks: list[dict[str, Any]] | None = None,
    ) -> Server:
        """Create a new server."""
        with self._lock:
            server_id = str(uuid4())
            server = Server(
                id=server_id,
                name=name,
                status=ServerStatus.BUILD,
                power_state=PowerState.NO_STATE,
                tenant_id=tenant_id or self._default_project_id,
                user_id=user_id or self._default_user_id,
                flavor_id=flavor_id,
                image_id=image_id,
                key_name=key_name,
                metadata=metadata or {},
                security_groups=security_groups or [{"name": "default"}],
                availability_zone=availability_zone,
                admin_pass=str(uuid4())[:12],
                progress=0,
            )

            # Simulate network assignment
            if networks:
                server.addresses = self._generate_addresses(networks)
            else:
                # Default network
                server.addresses = {
                    "private": [
                        {
                            "addr": f"10.0.0.{len(self._servers) + 10}",
                            "version": 4,
                            "OS-EXT-IPS:type": "fixed",
                            "OS-EXT-IPS-MAC:mac_addr": self._generate_mac(),
                        }
                    ]
                }

            self._servers[server_id] = server

            # Simulate immediate build completion for emulator
            self._complete_server_build(server_id)

            return server

    def _complete_server_build(self, server_id: str) -> None:
        """Simulate server build completion."""
        server = self._servers.get(server_id)
        if server:
            server.status = ServerStatus.ACTIVE
            server.power_state = PowerState.RUNNING
            server.progress = 100
            server.launched_at = datetime.utcnow()
            server.updated = datetime.utcnow()

    def _generate_addresses(
        self, networks: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate IP addresses for networks."""
        addresses: dict[str, list[dict[str, Any]]] = {}
        for i, network in enumerate(networks):
            net_name = network.get("uuid", f"network-{i}")
            addresses[net_name] = [
                {
                    "addr": f"10.0.{i}.{len(self._servers) + 10}",
                    "version": 4,
                    "OS-EXT-IPS:type": "fixed",
                    "OS-EXT-IPS-MAC:mac_addr": self._generate_mac(),
                }
            ]
        return addresses

    def _generate_mac(self) -> str:
        """Generate a random MAC address."""
        import random

        return "fa:16:3e:{:02x}:{:02x}:{:02x}".format(
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        )

    def get_server(self, server_id: str) -> Server | None:
        """Get a server by ID."""
        with self._lock:
            return self._servers.get(server_id)

    def list_servers(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        flavor: str | None = None,
        image: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
    ) -> list[Server]:
        """List servers with optional filtering."""
        with self._lock:
            servers = list(self._servers.values())

            # Apply filters
            if tenant_id:
                servers = [s for s in servers if s.tenant_id == tenant_id]
            if status:
                servers = [s for s in servers if s.status.value == status.upper()]
            if name:
                servers = [s for s in servers if name in s.name]
            if flavor:
                servers = [s for s in servers if s.flavor_id == flavor]
            if image:
                servers = [s for s in servers if s.image_id == image]

            # Exclude deleted servers
            servers = [s for s in servers if s.status != ServerStatus.DELETED]

            # Sort by created date
            servers.sort(key=lambda s: s.created)

            # Apply pagination
            if marker:
                marker_found = False
                filtered = []
                for server in servers:
                    if marker_found:
                        filtered.append(server)
                    elif server.id == marker:
                        marker_found = True
                servers = filtered

            if limit:
                servers = servers[:limit]

            return servers

    def update_server(
        self, server_id: str, name: str | None = None, metadata: dict[str, str] | None = None
    ) -> Server | None:
        """Update a server."""
        with self._lock:
            server = self._servers.get(server_id)
            if server:
                if name:
                    server.name = name
                if metadata is not None:
                    server.metadata = metadata
                server.updated = datetime.utcnow()
            return server

    def delete_server(self, server_id: str) -> bool:
        """Delete a server."""
        with self._lock:
            if server_id in self._servers:
                server = self._servers[server_id]
                server.status = ServerStatus.DELETED
                server.terminated_at = datetime.utcnow()
                server.updated = datetime.utcnow()
                del self._servers[server_id]
                return True
            return False

    # Server actions
    def server_action(self, server_id: str, action: str) -> bool:
        """Perform an action on a server."""
        with self._lock:
            server = self._servers.get(server_id)
            if not server:
                return False

            action_lower = action.lower()

            if action_lower == "start" or action_lower == "os-start":
                if server.status == ServerStatus.SHUTOFF:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "stop" or action_lower == "os-stop":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SHUTOFF
                    server.power_state = PowerState.SHUTDOWN
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "reboot":
                if server.status in [ServerStatus.ACTIVE, ServerStatus.SHUTOFF]:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "pause":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.PAUSED
                    server.power_state = PowerState.PAUSED
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "unpause":
                if server.status == ServerStatus.PAUSED:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "suspend":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SUSPENDED
                    server.power_state = PowerState.SUSPENDED
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "resume":
                if server.status == ServerStatus.SUSPENDED:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "shelve":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SHELVED
                    server.power_state = PowerState.SHUTDOWN
                    server.updated = datetime.utcnow()
                    return True

            elif action_lower == "unshelve":
                if server.status in [ServerStatus.SHELVED, ServerStatus.SHELVED_OFFLOADED]:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.utcnow()
                    return True

            return False

    # Flavor operations
    def get_flavor(self, flavor_id: str) -> Flavor | None:
        """Get a flavor by ID."""
        with self._lock:
            return self._flavors.get(flavor_id)

    def list_flavors(self, is_public: bool | None = None, limit: int | None = None) -> list[Flavor]:
        """List flavors with optional filtering."""
        with self._lock:
            flavors = list(self._flavors.values())

            if is_public is not None:
                flavors = [f for f in flavors if f.is_public == is_public]

            # Sort by ID (numeric IDs first, then alphabetically)
            flavors.sort(key=lambda f: (0, int(f.id)) if f.id.isdigit() else (1, f.id))

            if limit:
                flavors = flavors[:limit]

            return flavors

    def create_flavor(
        self,
        name: str,
        vcpus: int,
        ram: int,
        disk: int,
        flavor_id: str | None = None,
        ephemeral: int = 0,
        swap: int = 0,
        is_public: bool = True,
        description: str = "",
    ) -> Flavor:
        """Create a new flavor."""
        with self._lock:
            fid = flavor_id or str(uuid4())
            flavor = Flavor(
                id=fid,
                name=name,
                vcpus=vcpus,
                ram=ram,
                disk=disk,
                ephemeral=ephemeral,
                swap=swap,
                is_public=is_public,
                description=description,
            )
            self._flavors[fid] = flavor
            return flavor

    def delete_flavor(self, flavor_id: str) -> bool:
        """Delete a flavor."""
        with self._lock:
            if flavor_id in self._flavors:
                del self._flavors[flavor_id]
                return True
            return False

    # Image operations
    def get_image(self, image_id: str) -> Image | None:
        """Get an image by ID."""
        with self._lock:
            return self._images.get(image_id)

    def list_images(
        self, status: str | None = None, name: str | None = None, limit: int | None = None
    ) -> list[Image]:
        """List images with optional filtering."""
        with self._lock:
            images = list(self._images.values())

            if status:
                images = [i for i in images if i.status == status.upper()]
            if name:
                images = [i for i in images if name in i.name]

            # Sort by name
            images.sort(key=lambda i: i.name)

            if limit:
                images = images[:limit]

            return images

    def create_image(
        self,
        name: str,
        min_disk: int = 0,
        min_ram: int = 0,
        size: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> Image:
        """Create a new image."""
        with self._lock:
            image = Image(
                id=str(uuid4()),
                name=name,
                status="ACTIVE",
                min_disk=min_disk,
                min_ram=min_ram,
                size=size,
                metadata=metadata or {},
            )
            self._images[image.id] = image
            return image

    def delete_image(self, image_id: str) -> bool:
        """Delete an image."""
        with self._lock:
            if image_id in self._images:
                del self._images[image_id]
                return True
            return False

    # Keypair operations
    def create_keypair(
        self, name: str, user_id: str, public_key: str | None = None, key_type: str = "ssh"
    ) -> Keypair:
        """Create a new keypair."""
        with self._lock:
            import hashlib

            # Generate fingerprint from public key or create placeholder
            if public_key:
                fingerprint = hashlib.md5(public_key.encode()).hexdigest()
                fingerprint = ":".join(
                    fingerprint[i : i + 2] for i in range(0, len(fingerprint), 2)
                )
            else:
                # Generate a new keypair (simplified for emulator)
                public_key = f"ssh-rsa AAAA...emulated-key... {name}"
                fingerprint = "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff"

            keypair = Keypair(
                name=name,
                public_key=public_key,
                fingerprint=fingerprint,
                user_id=user_id,
                type=key_type,
            )
            key = f"{user_id}:{name}"
            self._keypairs[key] = keypair
            return keypair

    def get_keypair(self, name: str, user_id: str) -> Keypair | None:
        """Get a keypair by name and user."""
        with self._lock:
            key = f"{user_id}:{name}"
            return self._keypairs.get(key)

    def list_keypairs(self, user_id: str) -> list[Keypair]:
        """List keypairs for a user."""
        with self._lock:
            return [kp for kp in self._keypairs.values() if kp.user_id == user_id]

    def delete_keypair(self, name: str, user_id: str) -> bool:
        """Delete a keypair."""
        with self._lock:
            key = f"{user_id}:{name}"
            if key in self._keypairs:
                del self._keypairs[key]
                return True
            return False

    # Persistence
    def save(self) -> None:
        """Save database state to disk."""
        if not self.persist_path:
            return

        with self._lock:
            data = {
                "servers": {k: self._server_to_dict(v) for k, v in self._servers.items()},
                "flavors": {k: self._flavor_to_dict(v) for k, v in self._flavors.items()},
                "images": {k: self._image_to_dict(v) for k, v in self._images.items()},
                "keypairs": {k: self._keypair_to_dict(v) for k, v in self._keypairs.items()},
            }

            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)

    def load(self) -> None:
        """Load database state from disk."""
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if not path.exists():
            return

        with self._lock:
            with open(path) as f:
                json.load(f)

            # Restore state (simplified - would need proper deserialization)
            # This is a placeholder for full implementation

    def _server_to_dict(self, server: Server) -> dict[str, Any]:
        """Convert server to dictionary for persistence."""
        return {
            "id": server.id,
            "name": server.name,
            "status": server.status.value,
            "power_state": server.power_state.value,
            "tenant_id": server.tenant_id,
            "user_id": server.user_id,
            "flavor_id": server.flavor_id,
            "image_id": server.image_id,
            "host": server.host,
            "availability_zone": server.availability_zone,
            "key_name": server.key_name,
            "created": server.created.isoformat(),
            "updated": server.updated.isoformat(),
            "launched_at": server.launched_at.isoformat() if server.launched_at else None,
            "metadata": server.metadata,
            "addresses": server.addresses,
            "security_groups": server.security_groups,
        }

    def _flavor_to_dict(self, flavor: Flavor) -> dict[str, Any]:
        """Convert flavor to dictionary for persistence."""
        return {
            "id": flavor.id,
            "name": flavor.name,
            "vcpus": flavor.vcpus,
            "ram": flavor.ram,
            "disk": flavor.disk,
            "ephemeral": flavor.ephemeral,
            "swap": flavor.swap,
            "is_public": flavor.is_public,
        }

    def _image_to_dict(self, image: Image) -> dict[str, Any]:
        """Convert image to dictionary for persistence."""
        return {
            "id": image.id,
            "name": image.name,
            "status": image.status,
            "min_disk": image.min_disk,
            "min_ram": image.min_ram,
            "size": image.size,
            "metadata": image.metadata,
        }

    def _keypair_to_dict(self, keypair: Keypair) -> dict[str, Any]:
        """Convert keypair to dictionary for persistence."""
        return {
            "name": keypair.name,
            "public_key": keypair.public_key,
            "fingerprint": keypair.fingerprint,
            "user_id": keypair.user_id,
            "type": keypair.type,
        }

    # Domain operations
    def create_domain(
        self,
        name: str,
        description: str = "",
        enabled: bool = True,
        domain_id: str | None = None,
    ) -> Domain:
        """Create a new domain."""
        with self._lock:
            did = domain_id or str(uuid4())
            domain = Domain(
                id=did,
                name=name,
                description=description,
                enabled=enabled,
            )
            self._domains[did] = domain
            return domain

    def get_domain(self, domain_id: str) -> Domain | None:
        """Get a domain by ID."""
        with self._lock:
            return self._domains.get(domain_id)

    def get_domain_by_name(self, name: str) -> Domain | None:
        """Get a domain by name."""
        with self._lock:
            for domain in self._domains.values():
                if domain.name == name:
                    return domain
            return None

    def list_domains(
        self,
        enabled: bool | None = None,
        name: str | None = None,
    ) -> list[Domain]:
        """List domains with optional filtering."""
        with self._lock:
            domains = list(self._domains.values())
            if enabled is not None:
                domains = [d for d in domains if d.enabled == enabled]
            if name:
                domains = [d for d in domains if name in d.name]
            return domains

    def update_domain(
        self,
        domain_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> Domain | None:
        """Update a domain."""
        with self._lock:
            domain = self._domains.get(domain_id)
            if domain:
                if name is not None:
                    domain.name = name
                if description is not None:
                    domain.description = description
                if enabled is not None:
                    domain.enabled = enabled
            return domain

    def delete_domain(self, domain_id: str) -> bool:
        """Delete a domain."""
        with self._lock:
            if domain_id in self._domains and domain_id != "default":
                del self._domains[domain_id]
                return True
            return False

    # Project operations
    def create_project(
        self,
        name: str,
        domain_id: str = "default",
        description: str = "",
        enabled: bool = True,
        parent_id: str | None = None,
        is_domain: bool = False,
        project_id: str | None = None,
    ) -> Project:
        """Create a new project."""
        with self._lock:
            pid = project_id or str(uuid4())
            project = Project(
                id=pid,
                name=name,
                description=description,
                domain_id=domain_id,
                parent_id=parent_id,
                enabled=enabled,
                is_domain=is_domain,
            )
            self._projects[pid] = project
            return project

    def get_project(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        with self._lock:
            return self._projects.get(project_id)

    def get_project_by_name(self, name: str, domain_id: str = "default") -> Project | None:
        """Get a project by name and domain."""
        with self._lock:
            for project in self._projects.values():
                if project.name == name and project.domain_id == domain_id:
                    return project
            return None

    def list_projects(
        self,
        domain_id: str | None = None,
        enabled: bool | None = None,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> list[Project]:
        """List projects with optional filtering."""
        with self._lock:
            projects = list(self._projects.values())
            if domain_id:
                projects = [p for p in projects if p.domain_id == domain_id]
            if enabled is not None:
                projects = [p for p in projects if p.enabled == enabled]
            if name:
                projects = [p for p in projects if name in p.name]
            if parent_id:
                projects = [p for p in projects if p.parent_id == parent_id]
            return projects

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        domain_id: str | None = None,
    ) -> Project | None:
        """Update a project."""
        with self._lock:
            project = self._projects.get(project_id)
            if project:
                if name is not None:
                    project.name = name
                if description is not None:
                    project.description = description
                if enabled is not None:
                    project.enabled = enabled
                if domain_id is not None:
                    project.domain_id = domain_id
            return project

    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        with self._lock:
            if project_id in self._projects:
                del self._projects[project_id]
                # Remove associated role assignments
                self._role_assignments = [
                    ra for ra in self._role_assignments if ra.project_id != project_id
                ]
                return True
            return False

    # User operations
    def create_user(
        self,
        name: str,
        domain_id: str = "default",
        password: str = "",
        description: str = "",
        email: str = "",
        enabled: bool = True,
        default_project_id: str | None = None,
        user_id: str | None = None,
    ) -> User:
        """Create a new user."""
        with self._lock:
            import hashlib

            uid = user_id or str(uuid4())
            password_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""
            user = User(
                id=uid,
                name=name,
                description=description,
                domain_id=domain_id,
                default_project_id=default_project_id,
                enabled=enabled,
                password_hash=password_hash,
                email=email,
            )
            self._users[uid] = user
            return user

    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        with self._lock:
            return self._users.get(user_id)

    def get_user_by_name(self, name: str, domain_id: str = "default") -> User | None:
        """Get a user by name and domain."""
        with self._lock:
            for user in self._users.values():
                if user.name == name and user.domain_id == domain_id:
                    return user
            return None

    def list_users(
        self,
        domain_id: str | None = None,
        enabled: bool | None = None,
        name: str | None = None,
    ) -> list[User]:
        """List users with optional filtering."""
        with self._lock:
            users = list(self._users.values())
            if domain_id:
                users = [u for u in users if u.domain_id == domain_id]
            if enabled is not None:
                users = [u for u in users if u.enabled == enabled]
            if name:
                users = [u for u in users if name in u.name]
            return users

    def update_user(
        self,
        user_id: str,
        name: str | None = None,
        description: str | None = None,
        email: str | None = None,
        enabled: bool | None = None,
        password: str | None = None,
        default_project_id: str | None = None,
    ) -> User | None:
        """Update a user."""
        with self._lock:
            import hashlib

            user = self._users.get(user_id)
            if user:
                if name is not None:
                    user.name = name
                if description is not None:
                    user.description = description
                if email is not None:
                    user.email = email
                if enabled is not None:
                    user.enabled = enabled
                if password is not None:
                    user.password_hash = hashlib.sha256(password.encode()).hexdigest()
                if default_project_id is not None:
                    user.default_project_id = default_project_id
                user.updated_at = datetime.utcnow()
            return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        with self._lock:
            if user_id in self._users:
                del self._users[user_id]
                # Remove from groups
                for group_id in self._group_memberships:
                    self._group_memberships[group_id].discard(user_id)
                # Remove role assignments
                self._role_assignments = [
                    ra for ra in self._role_assignments if ra.user_id != user_id
                ]
                return True
            return False

    def verify_user_password(self, user_id: str, password: str) -> bool:
        """Verify a user's password."""
        with self._lock:
            import hashlib

            user = self._users.get(user_id)
            if user and user.password_hash:
                return user.password_hash == hashlib.sha256(password.encode()).hexdigest()
            # For testing, accept any password if no hash is set
            return True

    # Role operations
    def create_role(
        self,
        name: str,
        description: str = "",
        domain_id: str | None = None,
        role_id: str | None = None,
    ) -> Role:
        """Create a new role."""
        with self._lock:
            rid = role_id or str(uuid4())
            role = Role(
                id=rid,
                name=name,
                description=description,
                domain_id=domain_id,
            )
            self._roles[rid] = role
            return role

    def get_role(self, role_id: str) -> Role | None:
        """Get a role by ID."""
        with self._lock:
            return self._roles.get(role_id)

    def get_role_by_name(self, name: str, domain_id: str | None = None) -> Role | None:
        """Get a role by name."""
        with self._lock:
            for role in self._roles.values():
                if role.name == name:
                    if domain_id is None or role.domain_id == domain_id:
                        return role
            return None

    def list_roles(
        self,
        domain_id: str | None = None,
        name: str | None = None,
    ) -> list[Role]:
        """List roles with optional filtering."""
        with self._lock:
            roles = list(self._roles.values())
            if domain_id:
                roles = [r for r in roles if r.domain_id == domain_id]
            if name:
                roles = [r for r in roles if name in r.name]
            return roles

    def update_role(
        self,
        role_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> Role | None:
        """Update a role."""
        with self._lock:
            role = self._roles.get(role_id)
            if role:
                if name is not None:
                    role.name = name
                if description is not None:
                    role.description = description
            return role

    def delete_role(self, role_id: str) -> bool:
        """Delete a role."""
        with self._lock:
            if role_id in self._roles:
                del self._roles[role_id]
                # Remove role assignments
                self._role_assignments = [
                    ra for ra in self._role_assignments if ra.role_id != role_id
                ]
                return True
            return False

    # Role assignment operations
    def assign_role_to_user_on_project(
        self, role_id: str, user_id: str, project_id: str
    ) -> RoleAssignment:
        """Assign a role to a user on a project."""
        with self._lock:
            # Check if assignment already exists
            for ra in self._role_assignments:
                if ra.role_id == role_id and ra.user_id == user_id and ra.project_id == project_id:
                    return ra
            assignment = RoleAssignment(
                role_id=role_id,
                user_id=user_id,
                project_id=project_id,
            )
            self._role_assignments.append(assignment)
            return assignment

    def assign_role_to_user_on_domain(
        self, role_id: str, user_id: str, domain_id: str
    ) -> RoleAssignment:
        """Assign a role to a user on a domain."""
        with self._lock:
            for ra in self._role_assignments:
                if ra.role_id == role_id and ra.user_id == user_id and ra.domain_id == domain_id:
                    return ra
            assignment = RoleAssignment(
                role_id=role_id,
                user_id=user_id,
                domain_id=domain_id,
            )
            self._role_assignments.append(assignment)
            return assignment

    def assign_role_to_group_on_project(
        self, role_id: str, group_id: str, project_id: str
    ) -> RoleAssignment:
        """Assign a role to a group on a project."""
        with self._lock:
            for ra in self._role_assignments:
                if (
                    ra.role_id == role_id
                    and ra.group_id == group_id
                    and ra.project_id == project_id
                ):
                    return ra
            assignment = RoleAssignment(
                role_id=role_id,
                group_id=group_id,
                project_id=project_id,
            )
            self._role_assignments.append(assignment)
            return assignment

    def assign_role_to_group_on_domain(
        self, role_id: str, group_id: str, domain_id: str
    ) -> RoleAssignment:
        """Assign a role to a group on a domain."""
        with self._lock:
            for ra in self._role_assignments:
                if ra.role_id == role_id and ra.group_id == group_id and ra.domain_id == domain_id:
                    return ra
            assignment = RoleAssignment(
                role_id=role_id,
                group_id=group_id,
                domain_id=domain_id,
            )
            self._role_assignments.append(assignment)
            return assignment

    def revoke_role_from_user_on_project(self, role_id: str, user_id: str, project_id: str) -> bool:
        """Revoke a role from a user on a project."""
        with self._lock:
            for i, ra in enumerate(self._role_assignments):
                if ra.role_id == role_id and ra.user_id == user_id and ra.project_id == project_id:
                    del self._role_assignments[i]
                    return True
            return False

    def revoke_role_from_user_on_domain(self, role_id: str, user_id: str, domain_id: str) -> bool:
        """Revoke a role from a user on a domain."""
        with self._lock:
            for i, ra in enumerate(self._role_assignments):
                if ra.role_id == role_id and ra.user_id == user_id and ra.domain_id == domain_id:
                    del self._role_assignments[i]
                    return True
            return False

    def revoke_role_from_group_on_project(
        self, role_id: str, group_id: str, project_id: str
    ) -> bool:
        """Revoke a role from a group on a project."""
        with self._lock:
            for i, ra in enumerate(self._role_assignments):
                if (
                    ra.role_id == role_id
                    and ra.group_id == group_id
                    and ra.project_id == project_id
                ):
                    del self._role_assignments[i]
                    return True
            return False

    def revoke_role_from_group_on_domain(self, role_id: str, group_id: str, domain_id: str) -> bool:
        """Revoke a role from a group on a domain."""
        with self._lock:
            for i, ra in enumerate(self._role_assignments):
                if ra.role_id == role_id and ra.group_id == group_id and ra.domain_id == domain_id:
                    del self._role_assignments[i]
                    return True
            return False

    def check_role_assignment(
        self,
        role_id: str,
        user_id: str | None = None,
        group_id: str | None = None,
        project_id: str | None = None,
        domain_id: str | None = None,
    ) -> bool:
        """Check if a role assignment exists."""
        with self._lock:
            for ra in self._role_assignments:
                if ra.role_id != role_id:
                    continue
                if user_id and ra.user_id != user_id:
                    continue
                if group_id and ra.group_id != group_id:
                    continue
                if project_id and ra.project_id != project_id:
                    continue
                if domain_id and ra.domain_id != domain_id:
                    continue
                return True
            return False

    def list_role_assignments(
        self,
        user_id: str | None = None,
        group_id: str | None = None,
        project_id: str | None = None,
        domain_id: str | None = None,
        role_id: str | None = None,
    ) -> list[RoleAssignment]:
        """List role assignments with optional filtering."""
        with self._lock:
            assignments = self._role_assignments.copy()
            if user_id:
                assignments = [a for a in assignments if a.user_id == user_id]
            if group_id:
                assignments = [a for a in assignments if a.group_id == group_id]
            if project_id:
                assignments = [a for a in assignments if a.project_id == project_id]
            if domain_id:
                assignments = [a for a in assignments if a.domain_id == domain_id]
            if role_id:
                assignments = [a for a in assignments if a.role_id == role_id]
            return assignments

    def get_user_roles_on_project(self, user_id: str, project_id: str) -> list[dict[str, str]]:
        """Get all roles a user has on a project (including via groups)."""
        with self._lock:
            roles = []
            role_ids = set()

            # Direct assignments
            for ra in self._role_assignments:
                if ra.user_id == user_id and ra.project_id == project_id:
                    if ra.role_id not in role_ids:
                        role = self._roles.get(ra.role_id)
                        if role:
                            roles.append({"id": role.id, "name": role.name})
                            role_ids.add(ra.role_id)

            # Group assignments
            for group_id, members in self._group_memberships.items():
                if user_id in members:
                    for ra in self._role_assignments:
                        if ra.group_id == group_id and ra.project_id == project_id:
                            if ra.role_id not in role_ids:
                                role = self._roles.get(ra.role_id)
                                if role:
                                    roles.append({"id": role.id, "name": role.name})
                                    role_ids.add(ra.role_id)

            return roles

    # Group operations
    def create_group(
        self,
        name: str,
        domain_id: str = "default",
        description: str = "",
        group_id: str | None = None,
    ) -> Group:
        """Create a new group."""
        with self._lock:
            gid = group_id or str(uuid4())
            group = Group(
                id=gid,
                name=name,
                description=description,
                domain_id=domain_id,
            )
            self._groups[gid] = group
            self._group_memberships[gid] = set()
            return group

    def get_group(self, group_id: str) -> Group | None:
        """Get a group by ID."""
        with self._lock:
            return self._groups.get(group_id)

    def get_group_by_name(self, name: str, domain_id: str = "default") -> Group | None:
        """Get a group by name and domain."""
        with self._lock:
            for group in self._groups.values():
                if group.name == name and group.domain_id == domain_id:
                    return group
            return None

    def list_groups(
        self,
        domain_id: str | None = None,
        name: str | None = None,
    ) -> list[Group]:
        """List groups with optional filtering."""
        with self._lock:
            groups = list(self._groups.values())
            if domain_id:
                groups = [g for g in groups if g.domain_id == domain_id]
            if name:
                groups = [g for g in groups if name in g.name]
            return groups

    def update_group(
        self,
        group_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> Group | None:
        """Update a group."""
        with self._lock:
            group = self._groups.get(group_id)
            if group:
                if name is not None:
                    group.name = name
                if description is not None:
                    group.description = description
            return group

    def delete_group(self, group_id: str) -> bool:
        """Delete a group."""
        with self._lock:
            if group_id in self._groups:
                del self._groups[group_id]
                if group_id in self._group_memberships:
                    del self._group_memberships[group_id]
                # Remove role assignments
                self._role_assignments = [
                    ra for ra in self._role_assignments if ra.group_id != group_id
                ]
                return True
            return False

    def add_user_to_group(self, user_id: str, group_id: str) -> bool:
        """Add a user to a group."""
        with self._lock:
            if group_id in self._groups and user_id in self._users:
                if group_id not in self._group_memberships:
                    self._group_memberships[group_id] = set()
                self._group_memberships[group_id].add(user_id)
                return True
            return False

    def remove_user_from_group(self, user_id: str, group_id: str) -> bool:
        """Remove a user from a group."""
        with self._lock:
            if group_id in self._group_memberships:
                self._group_memberships[group_id].discard(user_id)
                return True
            return False

    def check_user_in_group(self, user_id: str, group_id: str) -> bool:
        """Check if a user is in a group."""
        with self._lock:
            return user_id in self._group_memberships.get(group_id, set())

    def list_users_in_group(self, group_id: str) -> list[User]:
        """List users in a group."""
        with self._lock:
            users = []
            for user_id in self._group_memberships.get(group_id, set()):
                user = self._users.get(user_id)
                if user:
                    users.append(user)
            return users

    def list_groups_for_user(self, user_id: str) -> list[Group]:
        """List groups a user belongs to."""
        with self._lock:
            groups = []
            for group_id, members in self._group_memberships.items():
                if user_id in members:
                    group = self._groups.get(group_id)
                    if group:
                        groups.append(group)
            return groups

    # Service operations
    def create_service(
        self,
        name: str,
        service_type: str,
        description: str = "",
        enabled: bool = True,
        service_id: str | None = None,
    ) -> Service:
        """Create a new service."""
        with self._lock:
            sid = service_id or str(uuid4())
            service = Service(
                id=sid,
                name=name,
                type=service_type,
                description=description,
                enabled=enabled,
            )
            self._services[sid] = service
            return service

    def get_service(self, service_id: str) -> Service | None:
        """Get a service by ID."""
        with self._lock:
            return self._services.get(service_id)

    def get_service_by_name(self, name: str) -> Service | None:
        """Get a service by name."""
        with self._lock:
            for service in self._services.values():
                if service.name == name:
                    return service
            return None

    def get_service_by_type(self, service_type: str) -> Service | None:
        """Get a service by type."""
        with self._lock:
            for service in self._services.values():
                if service.type == service_type:
                    return service
            return None

    def list_services(
        self,
        service_type: str | None = None,
        name: str | None = None,
    ) -> list[Service]:
        """List services with optional filtering."""
        with self._lock:
            services = list(self._services.values())
            if service_type:
                services = [s for s in services if s.type == service_type]
            if name:
                services = [s for s in services if name in s.name]
            return services

    def update_service(
        self,
        service_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> Service | None:
        """Update a service."""
        with self._lock:
            service = self._services.get(service_id)
            if service:
                if name is not None:
                    service.name = name
                if description is not None:
                    service.description = description
                if enabled is not None:
                    service.enabled = enabled
            return service

    def delete_service(self, service_id: str) -> bool:
        """Delete a service."""
        with self._lock:
            if service_id in self._services:
                del self._services[service_id]
                # Delete associated endpoints
                endpoints_to_delete = [
                    eid for eid, ep in self._endpoints.items() if ep.service_id == service_id
                ]
                for eid in endpoints_to_delete:
                    del self._endpoints[eid]
                return True
            return False

    # Endpoint operations
    def create_endpoint(
        self,
        service_id: str,
        interface: str,
        url: str,
        region_id: str | None = None,
        enabled: bool = True,
        endpoint_id: str | None = None,
    ) -> Endpoint:
        """Create a new endpoint."""
        with self._lock:
            eid = endpoint_id or str(uuid4())
            endpoint = Endpoint(
                id=eid,
                service_id=service_id,
                interface=interface,
                url=url,
                region_id=region_id,
                enabled=enabled,
            )
            self._endpoints[eid] = endpoint
            return endpoint

    def get_endpoint(self, endpoint_id: str) -> Endpoint | None:
        """Get an endpoint by ID."""
        with self._lock:
            return self._endpoints.get(endpoint_id)

    def list_endpoints(
        self,
        service_id: str | None = None,
        interface: str | None = None,
        region_id: str | None = None,
    ) -> list[Endpoint]:
        """List endpoints with optional filtering."""
        with self._lock:
            endpoints = list(self._endpoints.values())
            if service_id:
                endpoints = [e for e in endpoints if e.service_id == service_id]
            if interface:
                endpoints = [e for e in endpoints if e.interface == interface]
            if region_id:
                endpoints = [e for e in endpoints if e.region_id == region_id]
            return endpoints

    def update_endpoint(
        self,
        endpoint_id: str,
        interface: str | None = None,
        url: str | None = None,
        region_id: str | None = None,
        enabled: bool | None = None,
    ) -> Endpoint | None:
        """Update an endpoint."""
        with self._lock:
            endpoint = self._endpoints.get(endpoint_id)
            if endpoint:
                if interface is not None:
                    endpoint.interface = interface
                if url is not None:
                    endpoint.url = url
                if region_id is not None:
                    endpoint.region_id = region_id
                if enabled is not None:
                    endpoint.enabled = enabled
            return endpoint

    def delete_endpoint(self, endpoint_id: str) -> bool:
        """Delete an endpoint."""
        with self._lock:
            if endpoint_id in self._endpoints:
                del self._endpoints[endpoint_id]
                return True
            return False

    # Region operations
    def create_region(
        self,
        region_id: str,
        description: str = "",
        parent_region_id: str | None = None,
    ) -> Region:
        """Create a new region."""
        with self._lock:
            region = Region(
                id=region_id,
                description=description,
                parent_region_id=parent_region_id,
            )
            self._regions[region_id] = region
            return region

    def get_region(self, region_id: str) -> Region | None:
        """Get a region by ID."""
        with self._lock:
            return self._regions.get(region_id)

    def list_regions(self, parent_region_id: str | None = None) -> list[Region]:
        """List regions with optional filtering."""
        with self._lock:
            regions = list(self._regions.values())
            if parent_region_id:
                regions = [r for r in regions if r.parent_region_id == parent_region_id]
            return regions

    def update_region(
        self,
        region_id: str,
        description: str | None = None,
        parent_region_id: str | None = None,
    ) -> Region | None:
        """Update a region."""
        with self._lock:
            region = self._regions.get(region_id)
            if region:
                if description is not None:
                    region.description = description
                if parent_region_id is not None:
                    region.parent_region_id = parent_region_id
            return region

    def delete_region(self, region_id: str) -> bool:
        """Delete a region."""
        with self._lock:
            if region_id in self._regions:
                del self._regions[region_id]
                return True
            return False

    # Credential operations
    def create_credential(
        self,
        user_id: str,
        credential_type: str,
        blob: str,
        project_id: str | None = None,
        credential_id: str | None = None,
    ) -> Credential:
        """Create a new credential."""
        with self._lock:
            cid = credential_id or str(uuid4())
            credential = Credential(
                id=cid,
                user_id=user_id,
                project_id=project_id,
                type=credential_type,
                blob=blob,
            )
            self._credentials[cid] = credential
            return credential

    def get_credential(self, credential_id: str) -> Credential | None:
        """Get a credential by ID."""
        with self._lock:
            return self._credentials.get(credential_id)

    def list_credentials(
        self,
        user_id: str | None = None,
        credential_type: str | None = None,
    ) -> list[Credential]:
        """List credentials with optional filtering."""
        with self._lock:
            credentials = list(self._credentials.values())
            if user_id:
                credentials = [c for c in credentials if c.user_id == user_id]
            if credential_type:
                credentials = [c for c in credentials if c.type == credential_type]
            return credentials

    def update_credential(
        self,
        credential_id: str,
        blob: str | None = None,
        project_id: str | None = None,
    ) -> Credential | None:
        """Update a credential."""
        with self._lock:
            credential = self._credentials.get(credential_id)
            if credential:
                if blob is not None:
                    credential.blob = blob
                if project_id is not None:
                    credential.project_id = project_id
            return credential

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential."""
        with self._lock:
            if credential_id in self._credentials:
                del self._credentials[credential_id]
                return True
            return False

    # Reset operation
    def reset_keystone(self) -> None:
        """Reset all Keystone data to defaults."""
        with self._lock:
            self._domains.clear()
            self._projects.clear()
            self._users.clear()
            self._roles.clear()
            self._role_assignments.clear()
            self._groups.clear()
            self._group_memberships.clear()
            self._services.clear()
            self._endpoints.clear()
            self._regions.clear()
            self._credentials.clear()
            self._tokens.clear()
            self._init_default_keystone_data()

    def reset_cinder(self) -> None:
        """Reset all Cinder data to defaults."""
        with self._lock:
            self._volumes.clear()
            self._snapshots.clear()
            self._volume_types.clear()
            self._qos_specs.clear()
            self._init_default_volume_types()

    # Volume operations
    def create_volume(
        self,
        name: str,
        size: int,
        project_id: str,
        user_id: str,
        description: str = "",
        volume_type: str | None = None,
        availability_zone: str = "nova",
        metadata: dict[str, str] | None = None,
        source_volid: str | None = None,
        snapshot_id: str | None = None,
        image_id: str | None = None,
        multiattach: bool = False,
    ) -> Volume:
        """Create a new volume."""
        with self._lock:
            # Determine volume type
            if not volume_type:
                # Use default volume type
                for vt in self._volume_types.values():
                    if vt.name == "__DEFAULT__":
                        volume_type = vt.name
                        break
                else:
                    volume_type = "lvmdriver-1"

            volume = Volume(
                id=str(uuid4()),
                name=name,
                description=description,
                status=VolumeStatus.CREATING,
                size=size,
                volume_type=volume_type,
                availability_zone=availability_zone,
                bootable=image_id is not None,
                multiattach=multiattach,
                source_volid=source_volid,
                snapshot_id=snapshot_id,
                image_id=image_id,
                project_id=project_id,
                user_id=user_id,
                host="cinder-host@lvmdriver-1#lvmdriver-1",
                metadata=metadata or {},
            )

            self._volumes[volume.id] = volume

            # Simulate immediate availability for emulator
            self._complete_volume_creation(volume.id)

            return volume

    def _complete_volume_creation(self, volume_id: str) -> None:
        """Simulate volume creation completion."""
        volume = self._volumes.get(volume_id)
        if volume:
            volume.status = VolumeStatus.AVAILABLE
            volume.updated_at = datetime.utcnow()

    def get_volume(self, volume_id: str, project_id: str | None = None) -> Volume | None:
        """Get a volume by ID.

        Args:
            volume_id: The volume ID to look up.
            project_id: If provided, verify ownership.

        Returns:
            The volume if found and owned, else None.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if volume is None:
                return None
            if project_id is not None and volume.project_id != project_id:
                return None
            return volume

    def list_volumes(
        self,
        project_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
        all_tenants: bool = False,
    ) -> list[Volume]:
        """List volumes with optional filtering."""
        with self._lock:
            volumes = list(self._volumes.values())

            # Apply filters
            if project_id and not all_tenants:
                volumes = [v for v in volumes if v.project_id == project_id]
            if status:
                volumes = [v for v in volumes if v.status.value == status]
            if name:
                volumes = [v for v in volumes if name in v.name]

            # Sort by created date
            volumes.sort(key=lambda v: v.created_at)

            # Apply pagination
            if marker:
                marker_found = False
                filtered = []
                for volume in volumes:
                    if marker_found:
                        filtered.append(volume)
                    elif volume.id == marker:
                        marker_found = True
                volumes = filtered

            if limit:
                volumes = volumes[:limit]

            return volumes

    def update_volume(
        self,
        volume_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Volume | None:
        """Update a volume.

        Args:
            volume_id: The volume ID to update.
            project_id: If provided, verify ownership before updating.
            Other args: Fields to update.

        Returns:
            The updated volume if found and owned, else None.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return None
            if project_id is not None and volume.project_id != project_id:
                return None
            if name is not None:
                volume.name = name
            if description is not None:
                volume.description = description
            if metadata is not None:
                volume.metadata = metadata
            volume.updated_at = datetime.utcnow()
            return volume

    def delete_volume(self, volume_id: str, project_id: str | None = None) -> bool:
        """Delete a volume.

        Args:
            volume_id: The volume ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found, not owned, or in use.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return False
            if project_id is not None and volume.project_id != project_id:
                return False
            # Check if volume can be deleted
            if volume.status == VolumeStatus.IN_USE:
                return False
            if volume.attachments:
                return False
            del self._volumes[volume_id]
            return True

    def extend_volume(
        self, volume_id: str, new_size: int, project_id: str | None = None
    ) -> Volume | None:
        """Extend a volume to a new size.

        Args:
            volume_id: The volume ID to extend.
            new_size: The new size in GB.
            project_id: If provided, verify ownership.

        Returns:
            The extended volume if successful, else None.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return None
            if project_id is not None and volume.project_id != project_id:
                return None
            if new_size > volume.size and volume.status == VolumeStatus.AVAILABLE:
                volume.size = new_size
                volume.updated_at = datetime.utcnow()
                return volume
            return None

    def attach_volume(
        self,
        volume_id: str,
        server_id: str,
        project_id: str | None = None,
        device: str = "/dev/vdb",
        host_name: str = "compute-host-1",
    ) -> VolumeAttachment | None:
        """Attach a volume to a server.

        Args:
            volume_id: The volume ID to attach.
            server_id: The server to attach to.
            project_id: If provided, verify ownership.
            device: The device path.
            host_name: The compute host.

        Returns:
            The attachment if successful, else None.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return None
            if project_id is not None and volume.project_id != project_id:
                return None

            if volume.status != VolumeStatus.AVAILABLE and not volume.multiattach:
                return None

            attachment = VolumeAttachment(
                id=str(uuid4()),
                volume_id=volume_id,
                server_id=server_id,
                device=device,
                host_name=host_name,
            )

            volume.attachments.append(attachment)
            volume.status = VolumeStatus.IN_USE
            volume.updated_at = datetime.utcnow()

            return attachment

    def detach_volume(
        self, volume_id: str, attachment_id: str, project_id: str | None = None
    ) -> bool:
        """Detach a volume from a server.

        Args:
            volume_id: The volume ID to detach.
            attachment_id: The attachment ID.
            project_id: If provided, verify ownership.

        Returns:
            True if detached, False otherwise.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return False
            if project_id is not None and volume.project_id != project_id:
                return False

            for i, attachment in enumerate(volume.attachments):
                if attachment.id == attachment_id or attachment.attachment_id == attachment_id:
                    del volume.attachments[i]
                    if not volume.attachments:
                        volume.status = VolumeStatus.AVAILABLE
                    volume.updated_at = datetime.utcnow()
                    return True
            return False

    def set_volume_bootable(
        self, volume_id: str, bootable: bool, project_id: str | None = None
    ) -> Volume | None:
        """Set volume bootable flag.

        Args:
            volume_id: The volume ID.
            bootable: The bootable flag.
            project_id: If provided, verify ownership.

        Returns:
            The updated volume if successful, else None.
        """
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return None
            if project_id is not None and volume.project_id != project_id:
                return None
            volume.bootable = bootable
            volume.updated_at = datetime.utcnow()
            return volume

    # Snapshot operations
    def create_snapshot(
        self,
        volume_id: str,
        name: str,
        project_id: str,
        user_id: str,
        description: str = "",
        metadata: dict[str, str] | None = None,
        force: bool = False,
    ) -> Snapshot | None:
        """Create a volume snapshot."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return None

            # Check if volume can be snapshotted
            if not force and volume.status not in [VolumeStatus.AVAILABLE, VolumeStatus.IN_USE]:
                return None

            snapshot = Snapshot(
                id=str(uuid4()),
                name=name,
                description=description,
                status=SnapshotStatus.CREATING,
                volume_id=volume_id,
                size=volume.size,
                project_id=project_id,
                user_id=user_id,
                metadata=metadata or {},
            )

            self._snapshots[snapshot.id] = snapshot

            # Simulate immediate availability
            self._complete_snapshot_creation(snapshot.id)

            return snapshot

    def _complete_snapshot_creation(self, snapshot_id: str) -> None:
        """Simulate snapshot creation completion."""
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot:
            snapshot.status = SnapshotStatus.AVAILABLE
            snapshot.progress = "100%"
            snapshot.updated_at = datetime.utcnow()

    def get_snapshot(self, snapshot_id: str, project_id: str | None = None) -> Snapshot | None:
        """Get a snapshot by ID.

        Args:
            snapshot_id: The snapshot ID to look up.
            project_id: If provided, verify ownership.

        Returns:
            The snapshot if found and owned, else None.
        """
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                return None
            if project_id is not None and snapshot.project_id != project_id:
                return None
            return snapshot

    def list_snapshots(
        self,
        project_id: str | None = None,
        volume_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
        all_tenants: bool = False,
    ) -> list[Snapshot]:
        """List snapshots with optional filtering."""
        with self._lock:
            snapshots = list(self._snapshots.values())

            # Apply filters
            if project_id and not all_tenants:
                snapshots = [s for s in snapshots if s.project_id == project_id]
            if volume_id:
                snapshots = [s for s in snapshots if s.volume_id == volume_id]
            if status:
                snapshots = [s for s in snapshots if s.status.value == status]
            if name:
                snapshots = [s for s in snapshots if name in s.name]

            # Sort by created date
            snapshots.sort(key=lambda s: s.created_at)

            # Apply pagination
            if marker:
                marker_found = False
                filtered = []
                for snapshot in snapshots:
                    if marker_found:
                        filtered.append(snapshot)
                    elif snapshot.id == marker:
                        marker_found = True
                snapshots = filtered

            if limit:
                snapshots = snapshots[:limit]

            return snapshots

    def update_snapshot(
        self,
        snapshot_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Snapshot | None:
        """Update a snapshot.

        Args:
            snapshot_id: The snapshot ID to update.
            project_id: If provided, verify ownership before updating.
            Other args: Fields to update.

        Returns:
            The updated snapshot if found and owned, else None.
        """
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if not snapshot:
                return None
            if project_id is not None and snapshot.project_id != project_id:
                return None
            if name is not None:
                snapshot.name = name
            if description is not None:
                snapshot.description = description
            if metadata is not None:
                snapshot.metadata = metadata
            snapshot.updated_at = datetime.utcnow()
            return snapshot

    def delete_snapshot(self, snapshot_id: str, project_id: str | None = None) -> bool:
        """Delete a snapshot.

        Args:
            snapshot_id: The snapshot ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found or not owned.
        """
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if not snapshot:
                return False
            if project_id is not None and snapshot.project_id != project_id:
                return False
            del self._snapshots[snapshot_id]
            return True

    # Volume type operations
    def create_volume_type(
        self,
        name: str,
        description: str = "",
        is_public: bool = True,
        extra_specs: dict[str, str] | None = None,
    ) -> VolumeType:
        """Create a new volume type."""
        with self._lock:
            vtype = VolumeType(
                id=str(uuid4()),
                name=name,
                description=description,
                is_public=is_public,
                extra_specs=extra_specs or {},
            )
            self._volume_types[vtype.id] = vtype
            return vtype

    def get_volume_type(self, volume_type_id: str) -> VolumeType | None:
        """Get a volume type by ID."""
        with self._lock:
            return self._volume_types.get(volume_type_id)

    def get_volume_type_by_name(self, name: str) -> VolumeType | None:
        """Get a volume type by name."""
        with self._lock:
            for vtype in self._volume_types.values():
                if vtype.name == name:
                    return vtype
            return None

    def list_volume_types(
        self,
        is_public: bool | None = None,
    ) -> list[VolumeType]:
        """List volume types with optional filtering."""
        with self._lock:
            volume_types = list(self._volume_types.values())
            if is_public is not None:
                volume_types = [vt for vt in volume_types if vt.is_public == is_public]
            return volume_types

    def update_volume_type(
        self,
        volume_type_id: str,
        name: str | None = None,
        description: str | None = None,
        is_public: bool | None = None,
    ) -> VolumeType | None:
        """Update a volume type."""
        with self._lock:
            vtype = self._volume_types.get(volume_type_id)
            if vtype:
                if name is not None:
                    vtype.name = name
                if description is not None:
                    vtype.description = description
                if is_public is not None:
                    vtype.is_public = is_public
            return vtype

    def delete_volume_type(self, volume_type_id: str) -> bool:
        """Delete a volume type."""
        with self._lock:
            if volume_type_id in self._volume_types:
                del self._volume_types[volume_type_id]
                return True
            return False

    def set_volume_type_extra_specs(
        self, volume_type_id: str, extra_specs: dict[str, str]
    ) -> VolumeType | None:
        """Set extra specs for a volume type."""
        with self._lock:
            vtype = self._volume_types.get(volume_type_id)
            if vtype:
                vtype.extra_specs.update(extra_specs)
            return vtype

    def delete_volume_type_extra_spec(self, volume_type_id: str, key: str) -> bool:
        """Delete an extra spec from a volume type."""
        with self._lock:
            vtype = self._volume_types.get(volume_type_id)
            if vtype and key in vtype.extra_specs:
                del vtype.extra_specs[key]
                return True
            return False

    # QoS specs operations
    def create_qos_spec(
        self,
        name: str,
        consumer: str = "both",
        specs: dict[str, str] | None = None,
    ) -> QosSpec:
        """Create a new QoS spec."""
        with self._lock:
            qos = QosSpec(
                id=str(uuid4()),
                name=name,
                consumer=consumer,
                specs=specs or {},
            )
            self._qos_specs[qos.id] = qos
            return qos

    def get_qos_spec(self, qos_id: str) -> QosSpec | None:
        """Get a QoS spec by ID."""
        with self._lock:
            return self._qos_specs.get(qos_id)

    def list_qos_specs(self) -> list[QosSpec]:
        """List all QoS specs."""
        with self._lock:
            return list(self._qos_specs.values())

    def update_qos_spec(
        self,
        qos_id: str,
        specs: dict[str, str] | None = None,
    ) -> QosSpec | None:
        """Update a QoS spec."""
        with self._lock:
            qos = self._qos_specs.get(qos_id)
            if qos and specs:
                qos.specs.update(specs)
            return qos

    def delete_qos_spec(self, qos_id: str) -> bool:
        """Delete a QoS spec."""
        with self._lock:
            if qos_id in self._qos_specs:
                del self._qos_specs[qos_id]
                return True
            return False

    def associate_qos_spec_with_type(self, qos_id: str, volume_type_id: str) -> bool:
        """Associate a QoS spec with a volume type."""
        with self._lock:
            qos = self._qos_specs.get(qos_id)
            vtype = self._volume_types.get(volume_type_id)
            if qos and vtype:
                vtype.qos_specs_id = qos_id
                return True
            return False

    def disassociate_qos_spec_from_type(self, qos_id: str, volume_type_id: str) -> bool:
        """Disassociate a QoS spec from a volume type."""
        with self._lock:
            vtype = self._volume_types.get(volume_type_id)
            if vtype and vtype.qos_specs_id == qos_id:
                vtype.qos_specs_id = None
                return True
            return False

    # Volume limits/quotas
    def get_volume_limits(self, project_id: str) -> dict[str, Any]:
        """Get volume limits/quotas for a project."""
        with self._lock:
            # Count current usage
            volumes = [v for v in self._volumes.values() if v.project_id == project_id]
            snapshots = [s for s in self._snapshots.values() if s.project_id == project_id]
            total_gb = sum(v.size for v in volumes)
            snapshot_gb = sum(s.size for s in snapshots)

            return {
                "limits": {
                    "rate": [],
                    "absolute": {
                        "totalSnapshotsUsed": len(snapshots),
                        "maxTotalBackups": 10,
                        "maxTotalVolumeGigabytes": 1000,
                        "maxTotalSnapshots": 10,
                        "maxTotalBackupGigabytes": 1000,
                        "totalBackupGigabytesUsed": 0,
                        "maxTotalVolumes": 10,
                        "totalVolumesUsed": len(volumes),
                        "totalBackupsUsed": 0,
                        "totalGigabytesUsed": total_gb + snapshot_gb,
                    },
                }
            }

    # Glance Image operations
    def create_glance_image(
        self,
        name: str,
        owner: str,
        visibility: ImageVisibility = ImageVisibility.PRIVATE,
        min_disk: int = 0,
        min_ram: int = 0,
        protected: bool = False,
        container_format: ContainerFormat | None = None,
        disk_format: DiskFormat | None = None,
        tags: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        architecture: str | None = None,
        os_distro: str | None = None,
        os_version: str | None = None,
    ) -> GlanceImage:
        """Create a new Glance image."""
        with self._lock:
            image = GlanceImage(
                id=str(uuid4()),
                name=name,
                status=ImageStatus.QUEUED,
                visibility=visibility,
                protected=protected,
                owner=owner,
                min_disk=min_disk,
                min_ram=min_ram,
                container_format=container_format,
                disk_format=disk_format,
                tags=tags or [],
                properties=properties or {},
                architecture=architecture,
                os_distro=os_distro,
                os_version=os_version,
            )
            self._glance_images[image.id] = image
            self._image_members[image.id] = []
            return image

    def get_glance_image(self, image_id: str) -> GlanceImage | None:
        """Get a Glance image by ID."""
        with self._lock:
            return self._glance_images.get(image_id)

    def list_glance_images(
        self,
        owner: str | None = None,
        visibility: str | None = None,
        status: str | None = None,
        name: str | None = None,
        tag: str | None = None,
        member_status: str | None = None,
        limit: int | None = None,
        marker: str | None = None,
        sort_key: str = "created_at",
        sort_dir: str = "desc",
    ) -> list[GlanceImage]:
        """List Glance images with optional filtering."""
        with self._lock:
            images = list(self._glance_images.values())

            # Filter out deleted images
            images = [i for i in images if i.status != ImageStatus.DELETED]

            # Apply filters
            if owner:
                images = [i for i in images if i.owner == owner]
            if visibility:
                images = [i for i in images if i.visibility.value == visibility]
            if status:
                images = [i for i in images if i.status.value == status]
            if name:
                images = [i for i in images if name in i.name]
            if tag:
                images = [i for i in images if tag in i.tags]

            # Sort
            reverse = sort_dir == "desc"
            if sort_key == "created_at":
                images.sort(key=lambda i: i.created_at, reverse=reverse)
            elif sort_key == "updated_at":
                images.sort(key=lambda i: i.updated_at, reverse=reverse)
            elif sort_key == "name":
                images.sort(key=lambda i: i.name, reverse=reverse)
            elif sort_key == "size":
                images.sort(key=lambda i: i.size or 0, reverse=reverse)

            # Apply pagination
            if marker:
                marker_found = False
                filtered = []
                for image in images:
                    if marker_found:
                        filtered.append(image)
                    elif image.id == marker:
                        marker_found = True
                images = filtered

            if limit:
                images = images[:limit]

            return images

    def update_glance_image(
        self,
        image_id: str,
        name: str | None = None,
        visibility: ImageVisibility | None = None,
        min_disk: int | None = None,
        min_ram: int | None = None,
        protected: bool | None = None,
        container_format: ContainerFormat | None = None,
        disk_format: DiskFormat | None = None,
        tags: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        architecture: str | None = None,
        os_distro: str | None = None,
        os_version: str | None = None,
    ) -> GlanceImage | None:
        """Update a Glance image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return None

            if name is not None:
                image.name = name
            if visibility is not None:
                image.visibility = visibility
            if min_disk is not None:
                image.min_disk = min_disk
            if min_ram is not None:
                image.min_ram = min_ram
            if protected is not None:
                image.protected = protected
            if container_format is not None:
                image.container_format = container_format
            if disk_format is not None:
                image.disk_format = disk_format
            if tags is not None:
                image.tags = tags
            if properties is not None:
                image.properties.update(properties)
            if architecture is not None:
                image.architecture = architecture
            if os_distro is not None:
                image.os_distro = os_distro
            if os_version is not None:
                image.os_version = os_version

            image.updated_at = datetime.utcnow()

            # Update Nova image if active
            if image.status == ImageStatus.ACTIVE:
                self._images[image.id] = image.to_nova_image()

            return image

    def delete_glance_image(self, image_id: str) -> bool:
        """Delete a Glance image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if image.protected:
                return False

            image.status = ImageStatus.DELETED
            image.updated_at = datetime.utcnow()
            del self._glance_images[image_id]

            # Remove from Nova images
            if image_id in self._images:
                del self._images[image_id]

            # Remove image members
            if image_id in self._image_members:
                del self._image_members[image_id]

            return True

    def upload_image_data(
        self,
        image_id: str,
        size: int,
        checksum: str | None = None,
        os_hash_algo: str | None = None,
        os_hash_value: str | None = None,
    ) -> GlanceImage | None:
        """Simulate uploading image data."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return None

            if image.status != ImageStatus.QUEUED:
                return None

            # Simulate upload
            image.status = ImageStatus.ACTIVE
            image.size = size
            image.checksum = checksum or f"simulated-{image_id[:8]}"
            image.os_hash_algo = os_hash_algo or "sha512"
            image.os_hash_value = os_hash_value or f"simulated-hash-{image_id}"
            image.updated_at = datetime.utcnow()

            # Update Nova image
            self._images[image.id] = image.to_nova_image()

            return image

    def deactivate_glance_image(self, image_id: str) -> bool:
        """Deactivate a Glance image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if image.status != ImageStatus.ACTIVE:
                return False

            image.status = ImageStatus.DEACTIVATED
            image.updated_at = datetime.utcnow()

            # Remove from Nova images
            if image_id in self._images:
                del self._images[image_id]

            return True

    def reactivate_glance_image(self, image_id: str) -> bool:
        """Reactivate a Glance image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if image.status != ImageStatus.DEACTIVATED:
                return False

            image.status = ImageStatus.ACTIVE
            image.updated_at = datetime.utcnow()

            # Add back to Nova images
            self._images[image.id] = image.to_nova_image()

            return True

    # Image tags
    def add_image_tag(self, image_id: str, tag: str) -> bool:
        """Add a tag to an image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if tag not in image.tags:
                image.tags.append(tag)
                image.updated_at = datetime.utcnow()
            return True

    def delete_image_tag(self, image_id: str, tag: str) -> bool:
        """Delete a tag from an image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if tag in image.tags:
                image.tags.remove(tag)
                image.updated_at = datetime.utcnow()
                return True
            return False

    # Image members (for image sharing)
    def add_image_member(self, image_id: str, member_id: str) -> ImageMember | None:
        """Add a member to an image (share image with a project)."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return None

            if image.visibility != ImageVisibility.SHARED:
                # Need to set visibility to shared first
                return None

            # Check if member already exists
            members = self._image_members.get(image_id, [])
            for member in members:
                if member.member_id == member_id:
                    return member

            member = ImageMember(
                image_id=image_id,
                member_id=member_id,
                status="pending",
            )
            if image_id not in self._image_members:
                self._image_members[image_id] = []
            self._image_members[image_id].append(member)
            return member

    def get_image_member(self, image_id: str, member_id: str) -> ImageMember | None:
        """Get an image member."""
        with self._lock:
            members = self._image_members.get(image_id, [])
            for member in members:
                if member.member_id == member_id:
                    return member
            return None

    def list_image_members(self, image_id: str) -> list[ImageMember]:
        """List members of an image."""
        with self._lock:
            return self._image_members.get(image_id, []).copy()

    def update_image_member(self, image_id: str, member_id: str, status: str) -> ImageMember | None:
        """Update image member status."""
        with self._lock:
            members = self._image_members.get(image_id, [])
            for member in members:
                if member.member_id == member_id:
                    member.status = status
                    member.updated_at = datetime.utcnow()
                    return member
            return None

    def delete_image_member(self, image_id: str, member_id: str) -> bool:
        """Remove a member from an image."""
        with self._lock:
            members = self._image_members.get(image_id, [])
            for i, member in enumerate(members):
                if member.member_id == member_id:
                    del members[i]
                    return True
            return False

    def reset_glance(self) -> None:
        """Reset all Glance data to defaults."""
        with self._lock:
            self._glance_images.clear()
            self._image_members.clear()
            self._images.clear()
            self._init_default_glance_images()

    # Neutron operations

    def _init_default_neutron_data(self) -> None:
        """Initialize default Neutron resources."""

        # Create default security group
        default_sg = SecurityGroup(
            id=str(uuid4()),
            name="default",
            description="Default security group",
            project_id="admin",
        )
        # Add default egress rules
        for ethertype in ["IPv4", "IPv6"]:
            rule = SecurityGroupRule(
                id=str(uuid4()),
                security_group_id=default_sg.id,
                direction="egress",
                ethertype=ethertype,
                project_id="admin",
            )
            default_sg.security_group_rules.append(rule)
            self._security_group_rules[rule.id] = rule
        self._security_groups[default_sg.id] = default_sg

        # Create external network
        ext_network = Network(
            id=str(uuid4()),
            name="external",
            description="External network for floating IPs",
            external=True,
            shared=True,
            project_id="admin",
        )
        self._networks[ext_network.id] = ext_network

        # Create external subnet
        ext_subnet = Subnet(
            id=str(uuid4()),
            name="external-subnet",
            network_id=ext_network.id,
            cidr="203.0.113.0/24",
            gateway_ip="203.0.113.1",
            allocation_pools=[AllocationPool(start="203.0.113.10", end="203.0.113.254")],
            enable_dhcp=False,
            project_id="admin",
        )
        self._subnets[ext_subnet.id] = ext_subnet
        ext_network.subnets.append(ext_subnet.id)

        # Create default private network
        private_network = Network(
            id=str(uuid4()),
            name="private",
            description="Default private network",
            project_id="admin",
            shared=True,  # Shared so all projects can see/use it
        )
        self._networks[private_network.id] = private_network

        # Create private subnet
        private_subnet = Subnet(
            id=str(uuid4()),
            name="private-subnet",
            network_id=private_network.id,
            cidr="192.168.1.0/24",
            gateway_ip="192.168.1.1",
            allocation_pools=[AllocationPool(start="192.168.1.10", end="192.168.1.254")],
            dns_nameservers=["8.8.8.8", "8.8.4.4"],
            project_id="admin",
        )
        self._subnets[private_subnet.id] = private_subnet
        private_network.subnets.append(private_subnet.id)

    def _generate_mac_address(self) -> str:
        """Generate a random MAC address."""
        import random

        mac = [
            0xFA,
            0x16,
            0x3E,
            random.randint(0x00, 0x7F),
            random.randint(0x00, 0xFF),
            random.randint(0x00, 0xFF),
        ]
        return ":".join(f"{x:02x}" for x in mac)

    def _allocate_ip_from_subnet(self, subnet: Subnet) -> str | None:
        """Allocate an IP address from a subnet's allocation pool."""
        if not subnet.allocation_pools:
            return None

        pool = subnet.allocation_pools[0]
        # Simple IP allocation - just increment
        start_parts = pool.start.split(".")
        end_parts = pool.end.split(".")

        # Get all used IPs in this subnet
        used_ips = set()
        for port in self._ports.values():
            for fixed_ip in port.fixed_ips:
                if fixed_ip.subnet_id == subnet.id:
                    used_ips.add(fixed_ip.ip_address)

        # Find first available IP
        base = ".".join(start_parts[:3])
        start_host = int(start_parts[3])
        end_host = int(end_parts[3])

        for host in range(start_host, end_host + 1):
            ip = f"{base}.{host}"
            if ip not in used_ips:
                return ip

        return None

    # Network operations
    def create_network(
        self,
        name: str,
        project_id: str,
        description: str = "",
        admin_state_up: bool = True,
        shared: bool = False,
        external: bool = False,
        mtu: int = 1500,
        port_security_enabled: bool = True,
        provider_network_type: str | None = None,
        provider_physical_network: str | None = None,
        provider_segmentation_id: int | None = None,
    ) -> Network:
        """Create a new network."""
        with self._lock:
            network = Network(
                id=str(uuid4()),
                name=name,
                description=description,
                project_id=project_id,
                admin_state_up=admin_state_up,
                shared=shared,
                external=external,
                mtu=mtu,
                port_security_enabled=port_security_enabled,
                provider_network_type=provider_network_type,
                provider_physical_network=provider_physical_network,
                provider_segmentation_id=provider_segmentation_id,
            )
            self._networks[network.id] = network
            return network

    def get_network(self, network_id: str, project_id: str | None = None) -> Network | None:
        """Get a network by ID.

        Args:
            network_id: The network ID to look up.
            project_id: If provided, verify ownership (shared/external networks
                        are always accessible).

        Returns:
            The network if found and accessible, else None.
        """
        with self._lock:
            network = self._networks.get(network_id)
            if network is None:
                return None
            # Shared and external networks are accessible to all
            if project_id is not None and not network.shared and not network.external:
                if network.project_id != project_id:
                    return None
            return network

    def list_networks(
        self,
        project_id: str | None = None,
        name: str | None = None,
        shared: bool | None = None,
        external: bool | None = None,
        status: str | None = None,
    ) -> list[Network]:
        """List networks with optional filtering."""
        with self._lock:
            networks = list(self._networks.values())
            if project_id:
                networks = [n for n in networks if n.project_id == project_id or n.shared]
            if name:
                networks = [n for n in networks if n.name == name]
            if shared is not None:
                networks = [n for n in networks if n.shared == shared]
            if external is not None:
                networks = [n for n in networks if n.external == external]
            if status:
                networks = [n for n in networks if n.status.value == status]
            return networks

    def update_network(
        self,
        network_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        shared: bool | None = None,
        port_security_enabled: bool | None = None,
    ) -> Network | None:
        """Update a network.

        Args:
            network_id: The network ID to update.
            project_id: If provided, verify ownership before updating.
            name: New name for the network.
            description: New description.
            admin_state_up: New admin state.
            shared: New shared setting.
            port_security_enabled: New port security setting.

        Returns:
            The updated network if found and owned, else None.
        """
        with self._lock:
            network = self._networks.get(network_id)
            if not network:
                return None
            if project_id is not None and network.project_id != project_id:
                return None
            if name is not None:
                network.name = name
            if description is not None:
                network.description = description
            if admin_state_up is not None:
                network.admin_state_up = admin_state_up
            if shared is not None:
                network.shared = shared
            if port_security_enabled is not None:
                network.port_security_enabled = port_security_enabled
            network.updated_at = datetime.utcnow()
            return network

    def delete_network(self, network_id: str, project_id: str | None = None) -> bool:
        """Delete a network.

        Args:
            network_id: The network ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found, not owned, or has ports.
        """
        with self._lock:
            network = self._networks.get(network_id)
            if not network:
                return False
            if project_id is not None and network.project_id != project_id:
                return False
            # Check for ports
            for port in self._ports.values():
                if port.network_id == network_id:
                    return False  # Cannot delete network with ports
            # Delete associated subnets
            subnets_to_delete = [s.id for s in self._subnets.values() if s.network_id == network_id]
            for subnet_id in subnets_to_delete:
                del self._subnets[subnet_id]
            del self._networks[network_id]
            return True

    # Subnet operations
    def create_subnet(
        self,
        network_id: str,
        cidr: str,
        project_id: str,
        name: str = "",
        description: str = "",
        ip_version: int = 4,
        gateway_ip: str | None = None,
        allocation_pools: list[dict[str, str]] | None = None,
        dns_nameservers: list[str] | None = None,
        host_routes: list[dict[str, str]] | None = None,
        enable_dhcp: bool = True,
    ) -> Subnet | None:
        """Create a new subnet."""
        with self._lock:
            network = self._networks.get(network_id)
            if not network:
                return None

            # Parse allocation pools
            pools = []
            if allocation_pools:
                for pool in allocation_pools:
                    pools.append(AllocationPool(start=pool["start"], end=pool["end"]))

            # Auto-generate gateway if not provided
            if gateway_ip is None:
                parts = cidr.split("/")[0].split(".")
                gateway_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.1"

            subnet = Subnet(
                id=str(uuid4()),
                name=name,
                description=description,
                network_id=network_id,
                ip_version=ip_version,
                cidr=cidr,
                gateway_ip=gateway_ip,
                allocation_pools=pools,
                dns_nameservers=dns_nameservers or [],
                host_routes=host_routes or [],
                enable_dhcp=enable_dhcp,
                project_id=project_id,
            )
            self._subnets[subnet.id] = subnet
            network.subnets.append(subnet.id)
            return subnet

    def get_subnet(self, subnet_id: str, project_id: str | None = None) -> Subnet | None:
        """Get a subnet by ID.

        Args:
            subnet_id: The subnet ID to look up.
            project_id: If provided, verify ownership (subnets on shared networks
                        are accessible to all).

        Returns:
            The subnet if found and accessible, else None.
        """
        with self._lock:
            subnet = self._subnets.get(subnet_id)
            if subnet is None:
                return None
            if project_id is not None:
                # Check if subnet's network is shared
                network = self._networks.get(subnet.network_id)
                if network and (network.shared or network.external):
                    return subnet
                if subnet.project_id != project_id:
                    return None
            return subnet

    def list_subnets(
        self,
        project_id: str | None = None,
        network_id: str | None = None,
        name: str | None = None,
    ) -> list[Subnet]:
        """List subnets with optional filtering."""
        with self._lock:
            subnets = list(self._subnets.values())
            if project_id:
                subnets = [s for s in subnets if s.project_id == project_id]
            if network_id:
                subnets = [s for s in subnets if s.network_id == network_id]
            if name:
                subnets = [s for s in subnets if s.name == name]
            return subnets

    def update_subnet(
        self,
        subnet_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        gateway_ip: str | None = None,
        dns_nameservers: list[str] | None = None,
        host_routes: list[dict[str, str]] | None = None,
        enable_dhcp: bool | None = None,
    ) -> Subnet | None:
        """Update a subnet.

        Args:
            subnet_id: The subnet ID to update.
            project_id: If provided, verify ownership before updating.
            Other args: Fields to update.

        Returns:
            The updated subnet if found and owned, else None.
        """
        with self._lock:
            subnet = self._subnets.get(subnet_id)
            if not subnet:
                return None
            if project_id is not None and subnet.project_id != project_id:
                return None
            if name is not None:
                subnet.name = name
            if description is not None:
                subnet.description = description
            if gateway_ip is not None:
                subnet.gateway_ip = gateway_ip
            if dns_nameservers is not None:
                subnet.dns_nameservers = dns_nameservers
            if host_routes is not None:
                subnet.host_routes = host_routes
            if enable_dhcp is not None:
                subnet.enable_dhcp = enable_dhcp
            subnet.updated_at = datetime.utcnow()
            return subnet

    def delete_subnet(self, subnet_id: str, project_id: str | None = None) -> bool:
        """Delete a subnet.

        Args:
            subnet_id: The subnet ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found, not owned, or has ports.
        """
        with self._lock:
            subnet = self._subnets.get(subnet_id)
            if not subnet:
                return False
            if project_id is not None and subnet.project_id != project_id:
                return False
            # Check for ports using this subnet
            for port in self._ports.values():
                for fixed_ip in port.fixed_ips:
                    if fixed_ip.subnet_id == subnet_id:
                        return False
            # Remove from network
            network = self._networks.get(subnet.network_id)
            if network and subnet_id in network.subnets:
                network.subnets.remove(subnet_id)
            del self._subnets[subnet_id]
            return True

    # Port operations
    def create_port(
        self,
        network_id: str,
        project_id: str,
        name: str = "",
        description: str = "",
        admin_state_up: bool = True,
        mac_address: str | None = None,
        fixed_ips: list[dict[str, str]] | None = None,
        device_id: str = "",
        device_owner: str = "",
        security_groups: list[str] | None = None,
        port_security_enabled: bool = True,
    ) -> Port | None:
        """Create a new port."""
        with self._lock:
            network = self._networks.get(network_id)
            if not network:
                return None

            # Generate MAC address if not provided
            if not mac_address:
                mac_address = self._generate_mac_address()

            # Allocate IPs if not provided
            port_fixed_ips = []
            if fixed_ips:
                for fip in fixed_ips:
                    port_fixed_ips.append(
                        FixedIP(
                            subnet_id=fip.get("subnet_id", ""),
                            ip_address=fip.get("ip_address", ""),
                        )
                    )
            else:
                # Auto-allocate from first subnet
                for subnet_id in network.subnets:
                    subnet = self._subnets.get(subnet_id)
                    if subnet:
                        ip = self._allocate_ip_from_subnet(subnet)
                        if ip:
                            port_fixed_ips.append(FixedIP(subnet_id=subnet_id, ip_address=ip))
                            break

            port = Port(
                id=str(uuid4()),
                name=name,
                description=description,
                network_id=network_id,
                admin_state_up=admin_state_up,
                mac_address=mac_address,
                fixed_ips=port_fixed_ips,
                device_id=device_id,
                device_owner=device_owner,
                project_id=project_id,
                security_groups=security_groups or [],
                port_security_enabled=port_security_enabled,
            )
            self._ports[port.id] = port
            return port

    def get_port(self, port_id: str, project_id: str | None = None) -> Port | None:
        """Get a port by ID.

        Args:
            port_id: The port ID to look up.
            project_id: If provided, verify ownership.

        Returns:
            The port if found and owned, else None.
        """
        with self._lock:
            port = self._ports.get(port_id)
            if port is None:
                return None
            if project_id is not None and port.project_id != project_id:
                return None
            return port

    def list_ports(
        self,
        project_id: str | None = None,
        network_id: str | None = None,
        device_id: str | None = None,
        device_owner: str | None = None,
        status: str | None = None,
    ) -> list[Port]:
        """List ports with optional filtering."""
        with self._lock:
            ports = list(self._ports.values())
            if project_id:
                ports = [p for p in ports if p.project_id == project_id]
            if network_id:
                ports = [p for p in ports if p.network_id == network_id]
            if device_id:
                ports = [p for p in ports if p.device_id == device_id]
            if device_owner:
                ports = [p for p in ports if p.device_owner == device_owner]
            if status:
                ports = [p for p in ports if p.status.value == status]
            return ports

    def update_port(
        self,
        port_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        device_id: str | None = None,
        device_owner: str | None = None,
        security_groups: list[str] | None = None,
        port_security_enabled: bool | None = None,
    ) -> Port | None:
        """Update a port.

        Args:
            port_id: The port ID to update.
            project_id: If provided, verify ownership before updating.
            Other args: Fields to update.

        Returns:
            The updated port if found and owned, else None.
        """
        with self._lock:
            port = self._ports.get(port_id)
            if not port:
                return None
            if project_id is not None and port.project_id != project_id:
                return None
            if name is not None:
                port.name = name
            if description is not None:
                port.description = description
            if admin_state_up is not None:
                port.admin_state_up = admin_state_up
            if device_id is not None:
                port.device_id = device_id
            if device_owner is not None:
                port.device_owner = device_owner
            if security_groups is not None:
                port.security_groups = security_groups
            if port_security_enabled is not None:
                port.port_security_enabled = port_security_enabled
            port.updated_at = datetime.utcnow()
            return port

    def delete_port(self, port_id: str, project_id: str | None = None) -> bool:
        """Delete a port.

        Args:
            port_id: The port ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found or not owned.
        """
        with self._lock:
            port = self._ports.get(port_id)
            if not port:
                return False
            if project_id is not None and port.project_id != project_id:
                return False
            del self._ports[port_id]
            return True

    # Router operations
    def create_router(
        self,
        name: str,
        project_id: str,
        description: str = "",
        admin_state_up: bool = True,
        external_gateway_info: dict[str, Any] | None = None,
    ) -> Router:
        """Create a new router."""
        with self._lock:
            ext_gateway = None
            if external_gateway_info:
                ext_gateway = ExternalGatewayInfo(
                    network_id=external_gateway_info.get("network_id", ""),
                    enable_snat=external_gateway_info.get("enable_snat", True),
                    external_fixed_ips=external_gateway_info.get("external_fixed_ips", []),
                )

            router = Router(
                id=str(uuid4()),
                name=name,
                description=description,
                project_id=project_id,
                admin_state_up=admin_state_up,
                external_gateway_info=ext_gateway,
            )
            self._routers[router.id] = router
            return router

    def get_router(self, router_id: str, project_id: str | None = None) -> Router | None:
        """Get a router by ID.

        Args:
            router_id: The router ID to look up.
            project_id: If provided, verify ownership.

        Returns:
            The router if found and owned, else None.
        """
        with self._lock:
            router = self._routers.get(router_id)
            if router is None:
                return None
            if project_id is not None and router.project_id != project_id:
                return None
            return router

    def list_routers(
        self,
        project_id: str | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> list[Router]:
        """List routers with optional filtering."""
        with self._lock:
            routers = list(self._routers.values())
            if project_id:
                routers = [r for r in routers if r.project_id == project_id]
            if name:
                routers = [r for r in routers if r.name == name]
            if status:
                routers = [r for r in routers if r.status.value == status]
            return routers

    def update_router(
        self,
        router_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        external_gateway_info: dict[str, Any] | None = None,
        routes: list[dict[str, str]] | None = None,
    ) -> Router | None:
        """Update a router.

        Args:
            router_id: The router ID to update.
            project_id: If provided, verify ownership before updating.
            Other args: Fields to update.

        Returns:
            The updated router if found and owned, else None.
        """
        with self._lock:
            router = self._routers.get(router_id)
            if not router:
                return None
            if project_id is not None and router.project_id != project_id:
                return None
            if name is not None:
                router.name = name
            if description is not None:
                router.description = description
            if admin_state_up is not None:
                router.admin_state_up = admin_state_up
            if external_gateway_info is not None:
                if external_gateway_info:
                    router.external_gateway_info = ExternalGatewayInfo(
                        network_id=external_gateway_info.get("network_id", ""),
                        enable_snat=external_gateway_info.get("enable_snat", True),
                        external_fixed_ips=external_gateway_info.get("external_fixed_ips", []),
                    )
                else:
                    router.external_gateway_info = None
            if routes is not None:
                router.routes = routes
            router.updated_at = datetime.utcnow()
            return router

    def delete_router(self, router_id: str, project_id: str | None = None) -> bool:
        """Delete a router.

        Args:
            router_id: The router ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found, not owned, or has interfaces.
        """
        with self._lock:
            router = self._routers.get(router_id)
            if not router:
                return False
            if project_id is not None and router.project_id != project_id:
                return False
            # Check for interfaces
            for port in self._ports.values():
                if port.device_id == router_id:
                    return False
            del self._routers[router_id]
            return True

    def add_router_interface(
        self,
        router_id: str,
        project_id: str | None = None,
        subnet_id: str | None = None,
        port_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Add an interface to a router.

        Args:
            router_id: The router ID to add interface to.
            project_id: If provided, verify ownership before adding.
            subnet_id: The subnet to attach.
            port_id: The port to attach.

        Returns:
            Interface info if successful, None if router not found or not owned.
        """
        with self._lock:
            router = self._routers.get(router_id)
            if not router:
                return None
            if project_id is not None and router.project_id != project_id:
                return None

            if port_id:
                port = self._ports.get(port_id)
                if not port:
                    return None
                port.device_id = router_id
                port.device_owner = "network:router_interface"
                subnet_id = port.fixed_ips[0].subnet_id if port.fixed_ips else ""
            elif subnet_id:
                subnet = self._subnets.get(subnet_id)
                if not subnet:
                    return None
                # Create port for interface
                port = self.create_port(
                    network_id=subnet.network_id,
                    project_id=router.project_id,
                    device_id=router_id,
                    device_owner="network:router_interface",
                    fixed_ips=[{"subnet_id": subnet_id, "ip_address": subnet.gateway_ip or ""}],
                )
                if not port:
                    return None
                port_id = port.id

            return {
                "id": router_id,
                "subnet_id": subnet_id,
                "port_id": port_id,
                "tenant_id": router.project_id,
            }

    def remove_router_interface(
        self,
        router_id: str,
        project_id: str | None = None,
        subnet_id: str | None = None,
        port_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Remove an interface from a router.

        Args:
            router_id: The router ID to remove interface from.
            project_id: If provided, verify ownership before removing.
            subnet_id: The subnet to detach.
            port_id: The port to detach.

        Returns:
            Interface info if successful, None if router not found or not owned.
        """
        with self._lock:
            router = self._routers.get(router_id)
            if not router:
                return None
            if project_id is not None and router.project_id != project_id:
                return None

            if port_id:
                port = self._ports.get(port_id)
                if port and port.device_id == router_id:
                    del self._ports[port_id]
                    subnet_id = port.fixed_ips[0].subnet_id if port.fixed_ips else ""
            elif subnet_id:
                # Find and remove the port
                for pid, port in list(self._ports.items()):
                    if port.device_id == router_id:
                        for fixed_ip in port.fixed_ips:
                            if fixed_ip.subnet_id == subnet_id:
                                port_id = pid
                                del self._ports[pid]
                                break

            return {
                "id": router_id,
                "subnet_id": subnet_id,
                "port_id": port_id,
                "tenant_id": router.project_id,
            }

    # Floating IP operations
    def create_floating_ip(
        self,
        floating_network_id: str,
        project_id: str,
        description: str = "",
        port_id: str | None = None,
        fixed_ip_address: str | None = None,
        floating_ip_address: str | None = None,
    ) -> FloatingIP | None:
        """Create a new floating IP."""
        with self._lock:
            network = self._networks.get(floating_network_id)
            if not network or not network.external:
                return None

            # Allocate floating IP address
            if not floating_ip_address:
                floating_ip_address = f"203.0.113.{self._next_floating_ip}"
                self._next_floating_ip += 1

            fip = FloatingIP(
                id=str(uuid4()),
                description=description,
                floating_network_id=floating_network_id,
                floating_ip_address=floating_ip_address,
                port_id=port_id,
                fixed_ip_address=fixed_ip_address,
                project_id=project_id,
            )

            if port_id:
                fip.status = FloatingIPStatus.ACTIVE
                port = self._ports.get(port_id)
                if port and port.fixed_ips:
                    fip.fixed_ip_address = port.fixed_ips[0].ip_address

            self._floating_ips[fip.id] = fip
            return fip

    def get_floating_ip(
        self, floatingip_id: str, project_id: str | None = None
    ) -> FloatingIP | None:
        """Get a floating IP by ID.

        Args:
            floatingip_id: The floating IP ID to look up.
            project_id: If provided, verify ownership.

        Returns:
            The floating IP if found and owned, else None.
        """
        with self._lock:
            fip = self._floating_ips.get(floatingip_id)
            if fip is None:
                return None
            if project_id is not None and fip.project_id != project_id:
                return None
            return fip

    def list_floating_ips(
        self,
        project_id: str | None = None,
        floating_network_id: str | None = None,
        port_id: str | None = None,
        status: str | None = None,
    ) -> list[FloatingIP]:
        """List floating IPs with optional filtering."""
        with self._lock:
            fips = list(self._floating_ips.values())
            if project_id:
                fips = [f for f in fips if f.project_id == project_id]
            if floating_network_id:
                fips = [f for f in fips if f.floating_network_id == floating_network_id]
            if port_id:
                fips = [f for f in fips if f.port_id == port_id]
            if status:
                fips = [f for f in fips if f.status.value == status]
            return fips

    def update_floating_ip(
        self,
        floatingip_id: str,
        project_id: str | None = None,
        description: str | None = None,
        port_id: str | None = None,
    ) -> FloatingIP | None:
        """Update a floating IP (associate/disassociate).

        Args:
            floatingip_id: The floating IP ID to update.
            project_id: If provided, verify ownership before updating.
            description: New description.
            port_id: Port to associate (or empty string to disassociate).

        Returns:
            The updated floating IP if found and owned, else None.
        """
        with self._lock:
            fip = self._floating_ips.get(floatingip_id)
            if not fip:
                return None
            if project_id is not None and fip.project_id != project_id:
                return None
            if description is not None:
                fip.description = description
            if port_id is not None:
                fip.port_id = port_id if port_id else None
                if port_id:
                    port = self._ports.get(port_id)
                    if port and port.fixed_ips:
                        fip.fixed_ip_address = port.fixed_ips[0].ip_address
                    fip.status = FloatingIPStatus.ACTIVE
                else:
                    fip.fixed_ip_address = None
                    fip.status = FloatingIPStatus.DOWN
            fip.updated_at = datetime.utcnow()
            return fip

    def delete_floating_ip(self, floatingip_id: str, project_id: str | None = None) -> bool:
        """Delete a floating IP.

        Args:
            floatingip_id: The floating IP ID to delete.
            project_id: If provided, verify ownership before deleting.

        Returns:
            True if deleted, False if not found or not owned.
        """
        with self._lock:
            fip = self._floating_ips.get(floatingip_id)
            if not fip:
                return False
            if project_id is not None and fip.project_id != project_id:
                return False
            del self._floating_ips[floatingip_id]
            return True

    # Security Group operations
    def create_security_group(
        self,
        name: str,
        project_id: str,
        description: str = "",
    ) -> SecurityGroup:
        """Create a new security group."""
        with self._lock:
            sg = SecurityGroup(
                id=str(uuid4()),
                name=name,
                description=description,
                project_id=project_id,
            )
            # Add default egress rules
            for ethertype in ["IPv4", "IPv6"]:
                rule = SecurityGroupRule(
                    id=str(uuid4()),
                    security_group_id=sg.id,
                    direction="egress",
                    ethertype=ethertype,
                    project_id=project_id,
                )
                sg.security_group_rules.append(rule)
                self._security_group_rules[rule.id] = rule
            self._security_groups[sg.id] = sg
            return sg

    def get_or_create_default_security_group(self, project_id: str) -> SecurityGroup:
        """Get the default security group for a project, creating it if needed.

        In OpenStack, each project has its own 'default' security group that is
        created automatically when the project first accesses security groups.

        Args:
            project_id: The project ID to get/create the default security group for.

        Returns:
            The default security group for the project.
        """
        with self._lock:
            # Look for existing default security group for this project
            for sg in self._security_groups.values():
                if sg.name == "default" and sg.project_id == project_id:
                    return sg

            # Create a new default security group for this project
            sg = SecurityGroup(
                id=str(uuid4()),
                name="default",
                description="Default security group",
                project_id=project_id,
            )
            # Add default egress rules (allow all outbound traffic)
            for ethertype in ["IPv4", "IPv6"]:
                rule = SecurityGroupRule(
                    id=str(uuid4()),
                    security_group_id=sg.id,
                    direction="egress",
                    ethertype=ethertype,
                    project_id=project_id,
                )
                sg.security_group_rules.append(rule)
                self._security_group_rules[rule.id] = rule
            self._security_groups[sg.id] = sg
            return sg

    def get_security_group(
        self, security_group_id: str, project_id: str | None = None
    ) -> SecurityGroup | None:
        """Get a security group by ID.

        Args:
            security_group_id: The security group ID to look up.
            project_id: If provided, verify the security group belongs to this project.

        Returns:
            The security group if found (and owned by project_id if specified), else None.
        """
        with self._lock:
            sg = self._security_groups.get(security_group_id)
            if sg is None:
                return None
            if project_id is not None and sg.project_id != project_id:
                return None
            return sg

    def list_security_groups(
        self,
        project_id: str | None = None,
        name: str | None = None,
    ) -> list[SecurityGroup]:
        """List security groups with optional filtering."""
        with self._lock:
            sgs = list(self._security_groups.values())
            if project_id:
                sgs = [s for s in sgs if s.project_id == project_id]
            if name:
                sgs = [s for s in sgs if s.name == name]
            return sgs

    def update_security_group(
        self,
        security_group_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> SecurityGroup | None:
        """Update a security group.

        Args:
            security_group_id: The security group ID to update.
            project_id: If provided, verify the security group belongs to this project.
            name: New name for the security group.
            description: New description for the security group.

        Returns:
            The updated security group if found (and owned by project_id if specified),
            else None.
        """
        with self._lock:
            sg = self._security_groups.get(security_group_id)
            if not sg:
                return None
            if project_id is not None and sg.project_id != project_id:
                return None
            if name is not None:
                sg.name = name
            if description is not None:
                sg.description = description
            sg.updated_at = datetime.utcnow()
            return sg

    def delete_security_group(self, security_group_id: str, project_id: str | None = None) -> bool:
        """Delete a security group.

        Args:
            security_group_id: The security group ID to delete.
            project_id: If provided, verify the security group belongs to this project.

        Returns:
            True if deleted, False if not found, not owned, or is the default group.
        """
        with self._lock:
            sg = self._security_groups.get(security_group_id)
            if not sg:
                return False
            if project_id is not None and sg.project_id != project_id:
                return False
            if sg.name == "default":
                return False  # Cannot delete default security group
            # Delete associated rules
            for rule in sg.security_group_rules:
                if rule.id in self._security_group_rules:
                    del self._security_group_rules[rule.id]
            del self._security_groups[security_group_id]
            return True

    # Security Group Rule operations
    def create_security_group_rule(
        self,
        security_group_id: str,
        direction: str,
        project_id: str,
        ethertype: str = "IPv4",
        protocol: str | None = None,
        port_range_min: int | None = None,
        port_range_max: int | None = None,
        remote_ip_prefix: str | None = None,
        remote_group_id: str | None = None,
        description: str = "",
    ) -> SecurityGroupRule | None:
        """Create a new security group rule.

        Args:
            security_group_id: The security group to add the rule to.
            direction: 'ingress' or 'egress'.
            project_id: The requesting project's ID (must own the security group).
            ethertype: 'IPv4' or 'IPv6'.
            protocol: Protocol (tcp, udp, icmp, etc.) or None for all.
            port_range_min: Minimum port number.
            port_range_max: Maximum port number.
            remote_ip_prefix: CIDR for IP-based rules.
            remote_group_id: Reference to another security group.
            description: Rule description.

        Returns:
            The created rule if successful, None if security group not found
            or not owned by the project.
        """
        with self._lock:
            sg = self._security_groups.get(security_group_id)
            if not sg:
                return None
            # Verify the security group belongs to the requesting project
            if sg.project_id != project_id:
                return None

            rule = SecurityGroupRule(
                id=str(uuid4()),
                security_group_id=security_group_id,
                direction=direction,
                ethertype=ethertype,
                protocol=protocol,
                port_range_min=port_range_min,
                port_range_max=port_range_max,
                remote_ip_prefix=remote_ip_prefix,
                remote_group_id=remote_group_id,
                description=description,
                project_id=project_id,
            )
            sg.security_group_rules.append(rule)
            self._security_group_rules[rule.id] = rule
            return rule

    def get_security_group_rule(
        self, rule_id: str, project_id: str | None = None
    ) -> SecurityGroupRule | None:
        """Get a security group rule by ID.

        Args:
            rule_id: The rule ID to look up.
            project_id: If provided, verify the rule belongs to this project.

        Returns:
            The rule if found (and owned by project_id if specified), else None.
        """
        with self._lock:
            rule = self._security_group_rules.get(rule_id)
            if rule is None:
                return None
            if project_id is not None and rule.project_id != project_id:
                return None
            return rule

    def list_security_group_rules(
        self,
        project_id: str | None = None,
        security_group_id: str | None = None,
    ) -> list[SecurityGroupRule]:
        """List security group rules with optional filtering."""
        with self._lock:
            rules = list(self._security_group_rules.values())
            if project_id:
                rules = [r for r in rules if r.project_id == project_id]
            if security_group_id:
                rules = [r for r in rules if r.security_group_id == security_group_id]
            return rules

    def delete_security_group_rule(self, rule_id: str, project_id: str | None = None) -> bool:
        """Delete a security group rule.

        Args:
            rule_id: The rule ID to delete.
            project_id: If provided, verify the rule belongs to this project.

        Returns:
            True if deleted, False if not found or not owned by project.
        """
        with self._lock:
            rule = self._security_group_rules.get(rule_id)
            if not rule:
                return False
            if project_id is not None and rule.project_id != project_id:
                return False
            # Remove from parent security group
            sg = self._security_groups.get(rule.security_group_id)
            if sg:
                sg.security_group_rules = [r for r in sg.security_group_rules if r.id != rule_id]
            del self._security_group_rules[rule_id]
            return True

    def reset_neutron(self) -> None:
        """Reset all Neutron data to defaults."""
        with self._lock:
            self._networks.clear()
            self._subnets.clear()
            self._ports.clear()
            self._routers.clear()
            self._floating_ips.clear()
            self._security_groups.clear()
            self._security_group_rules.clear()
            self._next_floating_ip = 1
            self._init_default_neutron_data()

    # ==================== Server Group Operations ====================

    def create_server_group(
        self,
        name: str,
        policies: list[str],
        project_id: str,
        user_id: str,
        metadata: dict[str, str] | None = None,
    ) -> ServerGroup:
        """Create a new server group."""
        with self._lock:
            server_group = ServerGroup(
                name=name,
                policies=policies,
                project_id=project_id,
                user_id=user_id,
                metadata=metadata or {},
            )
            self._server_groups[server_group.id] = server_group
            return server_group

    def get_server_group(self, server_group_id: str) -> ServerGroup | None:
        """Get a server group by ID."""
        with self._lock:
            return self._server_groups.get(server_group_id)

    def list_server_groups(
        self,
        project_id: str | None = None,
        all_projects: bool = False,
    ) -> list[ServerGroup]:
        """List server groups with optional filtering."""
        with self._lock:
            groups = list(self._server_groups.values())
            if not all_projects and project_id:
                groups = [g for g in groups if g.project_id == project_id]
            return groups

    def delete_server_group(self, server_group_id: str) -> bool:
        """Delete a server group."""
        with self._lock:
            if server_group_id in self._server_groups:
                del self._server_groups[server_group_id]
                return True
            return False

    def add_server_to_group(self, server_group_id: str, server_id: str) -> bool:
        """Add a server to a server group."""
        with self._lock:
            group = self._server_groups.get(server_group_id)
            if not group:
                return False
            if server_id not in group.members:
                group.members.append(server_id)
            return True

    def remove_server_from_group(self, server_group_id: str, server_id: str) -> bool:
        """Remove a server from a server group."""
        with self._lock:
            group = self._server_groups.get(server_group_id)
            if not group:
                return False
            if server_id in group.members:
                group.members.remove(server_id)
            return True

    # ==================== Nova Quota Operations ====================

    def get_nova_quota(self, project_id: str) -> NovaQuota:
        """Get Nova quotas for a project (creates default if not exists)."""
        with self._lock:
            if project_id not in self._nova_quotas:
                self._nova_quotas[project_id] = NovaQuota(project_id=project_id)
            return self._nova_quotas[project_id]

    def update_nova_quota(
        self,
        project_id: str,
        instances: int | None = None,
        cores: int | None = None,
        ram: int | None = None,
        metadata_items: int | None = None,
        injected_files: int | None = None,
        injected_file_content_bytes: int | None = None,
        injected_file_path_bytes: int | None = None,
        key_pairs: int | None = None,
        server_groups: int | None = None,
        server_group_members: int | None = None,
    ) -> NovaQuota:
        """Update Nova quotas for a project."""
        with self._lock:
            quota = self.get_nova_quota(project_id)
            if instances is not None:
                quota.instances = instances
            if cores is not None:
                quota.cores = cores
            if ram is not None:
                quota.ram = ram
            if metadata_items is not None:
                quota.metadata_items = metadata_items
            if injected_files is not None:
                quota.injected_files = injected_files
            if injected_file_content_bytes is not None:
                quota.injected_file_content_bytes = injected_file_content_bytes
            if injected_file_path_bytes is not None:
                quota.injected_file_path_bytes = injected_file_path_bytes
            if key_pairs is not None:
                quota.key_pairs = key_pairs
            if server_groups is not None:
                quota.server_groups = server_groups
            if server_group_members is not None:
                quota.server_group_members = server_group_members
            return quota

    def delete_nova_quota(self, project_id: str) -> bool:
        """Delete Nova quota for a project (resets to defaults)."""
        with self._lock:
            if project_id in self._nova_quotas:
                del self._nova_quotas[project_id]
                return True
            return False

    def get_nova_quota_usage(self, project_id: str) -> dict[str, int]:
        """Get current Nova quota usage for a project."""
        with self._lock:
            servers = [s for s in self._servers.values() if s.tenant_id == project_id]
            total_cores = 0
            total_ram = 0
            for server in servers:
                flavor = self._flavors.get(server.flavor_id)
                if flavor:
                    total_cores += flavor.vcpus
                    total_ram += flavor.ram

            keypairs = [k for k in self._keypairs.values() if k.user_id.startswith(project_id)]
            server_groups = [g for g in self._server_groups.values() if g.project_id == project_id]

            return {
                "instances": len(servers),
                "cores": total_cores,
                "ram": total_ram,
                "key_pairs": len(keypairs),
                "server_groups": len(server_groups),
            }

    # ==================== Neutron Quota Operations ====================

    def get_neutron_quota(self, project_id: str) -> NeutronQuota:
        """Get Neutron quotas for a project (creates default if not exists)."""
        with self._lock:
            if project_id not in self._neutron_quotas:
                self._neutron_quotas[project_id] = NeutronQuota(project_id=project_id)
            return self._neutron_quotas[project_id]

    def update_neutron_quota(
        self,
        project_id: str,
        network: int | None = None,
        subnet: int | None = None,
        subnetpool: int | None = None,
        port: int | None = None,
        router: int | None = None,
        floatingip: int | None = None,
        security_group: int | None = None,
        security_group_rule: int | None = None,
        rbac_policy: int | None = None,
    ) -> NeutronQuota:
        """Update Neutron quotas for a project."""
        with self._lock:
            quota = self.get_neutron_quota(project_id)
            if network is not None:
                quota.network = network
            if subnet is not None:
                quota.subnet = subnet
            if subnetpool is not None:
                quota.subnetpool = subnetpool
            if port is not None:
                quota.port = port
            if router is not None:
                quota.router = router
            if floatingip is not None:
                quota.floatingip = floatingip
            if security_group is not None:
                quota.security_group = security_group
            if security_group_rule is not None:
                quota.security_group_rule = security_group_rule
            if rbac_policy is not None:
                quota.rbac_policy = rbac_policy
            return quota

    def delete_neutron_quota(self, project_id: str) -> bool:
        """Delete Neutron quota for a project (resets to defaults)."""
        with self._lock:
            if project_id in self._neutron_quotas:
                del self._neutron_quotas[project_id]
                return True
            return False

    def get_neutron_quota_usage(self, project_id: str) -> dict[str, int]:
        """Get current Neutron quota usage for a project."""
        with self._lock:
            networks = [n for n in self._networks.values() if n.project_id == project_id]
            subnets = [s for s in self._subnets.values() if s.project_id == project_id]
            ports = [p for p in self._ports.values() if p.project_id == project_id]
            routers = [r for r in self._routers.values() if r.project_id == project_id]
            floating_ips = [f for f in self._floating_ips.values() if f.project_id == project_id]
            security_groups = [
                sg for sg in self._security_groups.values() if sg.project_id == project_id
            ]
            security_group_rules = [
                r for r in self._security_group_rules.values() if r.project_id == project_id
            ]

            return {
                "network": len(networks),
                "subnet": len(subnets),
                "subnetpool": 0,
                "port": len(ports),
                "router": len(routers),
                "floatingip": len(floating_ips),
                "security_group": len(security_groups),
                "security_group_rule": len(security_group_rules),
                "rbac_policy": 0,
            }

    # ==================== Cinder Quota Operations ====================

    def get_cinder_quota(self, project_id: str) -> CinderQuota:
        """Get Cinder quotas for a project (creates default if not exists)."""
        with self._lock:
            if project_id not in self._cinder_quotas:
                self._cinder_quotas[project_id] = CinderQuota(project_id=project_id)
            return self._cinder_quotas[project_id]

    def update_cinder_quota(
        self,
        project_id: str,
        volumes: int | None = None,
        snapshots: int | None = None,
        gigabytes: int | None = None,
        per_volume_gigabytes: int | None = None,
        backups: int | None = None,
        backup_gigabytes: int | None = None,
        groups: int | None = None,
    ) -> CinderQuota:
        """Update Cinder quotas for a project."""
        with self._lock:
            quota = self.get_cinder_quota(project_id)
            if volumes is not None:
                quota.volumes = volumes
            if snapshots is not None:
                quota.snapshots = snapshots
            if gigabytes is not None:
                quota.gigabytes = gigabytes
            if per_volume_gigabytes is not None:
                quota.per_volume_gigabytes = per_volume_gigabytes
            if backups is not None:
                quota.backups = backups
            if backup_gigabytes is not None:
                quota.backup_gigabytes = backup_gigabytes
            if groups is not None:
                quota.groups = groups
            return quota

    def delete_cinder_quota(self, project_id: str) -> bool:
        """Delete Cinder quota for a project (resets to defaults)."""
        with self._lock:
            if project_id in self._cinder_quotas:
                del self._cinder_quotas[project_id]
                return True
            return False

    def get_cinder_quota_usage(self, project_id: str) -> dict[str, int]:
        """Get current Cinder quota usage for a project."""
        with self._lock:
            volumes = [v for v in self._volumes.values() if v.project_id == project_id]
            snapshots = [s for s in self._snapshots.values() if s.project_id == project_id]
            total_gigabytes = sum(v.size for v in volumes)

            return {
                "volumes": len(volumes),
                "snapshots": len(snapshots),
                "gigabytes": total_gigabytes,
                "backups": 0,
                "backup_gigabytes": 0,
                "groups": 0,
            }

    # ==================== RBAC Policy Operations ====================

    def create_rbac_policy(
        self,
        object_type: str,
        object_id: str,
        target_project: str,
        project_id: str,
        action: str = "access_as_shared",
    ) -> RbacPolicy:
        """Create a new RBAC policy."""
        with self._lock:
            policy = RbacPolicy(
                object_type=object_type,
                object_id=object_id,
                target_project=target_project,
                project_id=project_id,
                action=action,
            )
            self._rbac_policies[policy.id] = policy

            # If sharing a network, update the network's shared flag
            if object_type == "network" and target_project == "*":
                network = self._networks.get(object_id)
                if network:
                    network.shared = True

            return policy

    def get_rbac_policy(self, policy_id: str) -> RbacPolicy | None:
        """Get an RBAC policy by ID."""
        with self._lock:
            return self._rbac_policies.get(policy_id)

    def list_rbac_policies(
        self,
        project_id: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        target_project: str | None = None,
        action: str | None = None,
    ) -> list[RbacPolicy]:
        """List RBAC policies with optional filtering."""
        with self._lock:
            policies = list(self._rbac_policies.values())
            if project_id:
                policies = [p for p in policies if p.project_id == project_id]
            if object_type:
                policies = [p for p in policies if p.object_type == object_type]
            if object_id:
                policies = [p for p in policies if p.object_id == object_id]
            if target_project:
                policies = [p for p in policies if p.target_project == target_project]
            if action:
                policies = [p for p in policies if p.action == action]
            return policies

    def update_rbac_policy(
        self,
        policy_id: str,
        target_project: str | None = None,
    ) -> RbacPolicy | None:
        """Update an RBAC policy (only target_project can be updated)."""
        with self._lock:
            policy = self._rbac_policies.get(policy_id)
            if not policy:
                return None

            old_target = policy.target_project

            if target_project is not None:
                policy.target_project = target_project
                policy.updated_at = datetime.utcnow()

                # Update network shared flag if applicable
                if policy.object_type == "network":
                    network = self._networks.get(policy.object_id)
                    if network:
                        if target_project == "*":
                            network.shared = True
                        elif old_target == "*":
                            # Check if any other policy still shares this network
                            other_policies = [
                                p
                                for p in self._rbac_policies.values()
                                if p.object_id == policy.object_id
                                and p.target_project == "*"
                                and p.id != policy_id
                            ]
                            if not other_policies:
                                network.shared = False

            return policy

    def delete_rbac_policy(self, policy_id: str) -> bool:
        """Delete an RBAC policy."""
        with self._lock:
            policy = self._rbac_policies.get(policy_id)
            if not policy:
                return False

            # Update network shared flag if applicable
            if policy.object_type == "network" and policy.target_project == "*":
                network = self._networks.get(policy.object_id)
                if network:
                    # Check if any other policy still shares this network
                    other_policies = [
                        p
                        for p in self._rbac_policies.values()
                        if p.object_id == policy.object_id
                        and p.target_project == "*"
                        and p.id != policy_id
                    ]
                    if not other_policies:
                        network.shared = False

            del self._rbac_policies[policy_id]
            return True

    # Octavia Load Balancer operations

    def create_load_balancer(
        self,
        name: str,
        project_id: str,
        vip_subnet_id: str | None = None,
        vip_network_id: str | None = None,
        vip_address: str | None = None,
        description: str = "",
        admin_state_up: bool = True,
        flavor_id: str | None = None,
        provider: str = "amphora",
        availability_zone: str | None = None,
        tags: list[str] | None = None,
    ) -> LoadBalancer:
        """Create a new load balancer."""
        with self._lock:
            lb_id = str(uuid4())

            # Generate VIP address if not provided
            if not vip_address:
                vip_address = f"192.168.100.{self._next_lb_vip}"
                self._next_lb_vip += 1

            # Create a VIP port
            vip_port_id = str(uuid4())

            lb = LoadBalancer(
                id=lb_id,
                name=name,
                description=description,
                admin_state_up=admin_state_up,
                project_id=project_id,
                vip_subnet_id=vip_subnet_id or "",
                vip_network_id=vip_network_id or "",
                vip_port_id=vip_port_id,
                vip_address=vip_address,
                flavor_id=flavor_id,
                provider=provider,
                availability_zone=availability_zone,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._load_balancers[lb_id] = lb
            return lb

    def get_load_balancer(self, lb_id: str, project_id: str | None = None) -> LoadBalancer | None:
        """Get a load balancer by ID."""
        with self._lock:
            lb = self._load_balancers.get(lb_id)
            if lb is None:
                return None
            if project_id is not None and lb.project_id != project_id:
                return None
            return lb

    def list_load_balancers(
        self,
        project_id: str | None = None,
        name: str | None = None,
        vip_address: str | None = None,
        vip_subnet_id: str | None = None,
        provisioning_status: str | None = None,
        operating_status: str | None = None,
    ) -> list[LoadBalancer]:
        """List load balancers with optional filtering."""
        with self._lock:
            lbs = list(self._load_balancers.values())

            if project_id:
                lbs = [lb for lb in lbs if lb.project_id == project_id]
            if name:
                lbs = [lb for lb in lbs if lb.name == name]
            if vip_address:
                lbs = [lb for lb in lbs if lb.vip_address == vip_address]
            if vip_subnet_id:
                lbs = [lb for lb in lbs if lb.vip_subnet_id == vip_subnet_id]
            if provisioning_status:
                lbs = [lb for lb in lbs if lb.provisioning_status.value == provisioning_status]
            if operating_status:
                lbs = [lb for lb in lbs if lb.operating_status.value == operating_status]

            return lbs

    def update_load_balancer(
        self,
        lb_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        tags: list[str] | None = None,
    ) -> LoadBalancer | None:
        """Update a load balancer."""
        with self._lock:
            lb = self._load_balancers.get(lb_id)
            if not lb:
                return None
            if project_id is not None and lb.project_id != project_id:
                return None

            if name is not None:
                lb.name = name
            if description is not None:
                lb.description = description
            if admin_state_up is not None:
                lb.admin_state_up = admin_state_up
            if tags is not None:
                lb.tags = tags

            return lb

    def delete_load_balancer(
        self, lb_id: str, project_id: str | None = None, cascade: bool = False
    ) -> bool:
        """Delete a load balancer."""
        with self._lock:
            lb = self._load_balancers.get(lb_id)
            if not lb:
                return False
            if project_id is not None and lb.project_id != project_id:
                return False

            if cascade:
                # Delete all associated resources
                for listener in list(lb.listeners):
                    self.delete_listener(listener.id, cascade=True)
                for pool in list(lb.pools):
                    self.delete_pool(pool.id)

            del self._load_balancers[lb_id]
            return True

    # Listener operations

    def create_listener(
        self,
        name: str,
        loadbalancer_id: str,
        protocol: str,
        protocol_port: int,
        project_id: str,
        description: str = "",
        admin_state_up: bool = True,
        connection_limit: int = -1,
        default_pool_id: str | None = None,
        default_tls_container_ref: str | None = None,
        sni_container_refs: list[str] | None = None,
        insert_headers: dict[str, str] | None = None,
        timeout_client_data: int | None = None,
        timeout_member_connect: int | None = None,
        timeout_member_data: int | None = None,
        timeout_tcp_inspect: int | None = None,
        allowed_cidrs: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Listener | None:
        """Create a new listener."""
        with self._lock:
            lb = self._load_balancers.get(loadbalancer_id)
            if not lb:
                return None

            listener_id = str(uuid4())
            listener = Listener(
                id=listener_id,
                name=name,
                description=description,
                admin_state_up=admin_state_up,
                project_id=project_id,
                protocol=ListenerProtocol(protocol),
                protocol_port=protocol_port,
                connection_limit=connection_limit,
                default_pool_id=default_pool_id,
                default_tls_container_ref=default_tls_container_ref,
                sni_container_refs=sni_container_refs or [],
                insert_headers=insert_headers or {},
                timeout_client_data=timeout_client_data,
                timeout_member_connect=timeout_member_connect,
                timeout_member_data=timeout_member_data,
                timeout_tcp_inspect=timeout_tcp_inspect,
                allowed_cidrs=allowed_cidrs or [],
                loadbalancer_id=loadbalancer_id,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._listeners[listener_id] = listener
            lb.listeners.append(listener)
            return listener

    def get_listener(self, listener_id: str, project_id: str | None = None) -> Listener | None:
        """Get a listener by ID."""
        with self._lock:
            listener = self._listeners.get(listener_id)
            if listener is None:
                return None
            if project_id is not None and listener.project_id != project_id:
                return None
            return listener

    def list_listeners(
        self,
        project_id: str | None = None,
        loadbalancer_id: str | None = None,
        name: str | None = None,
        protocol: str | None = None,
        protocol_port: int | None = None,
    ) -> list[Listener]:
        """List listeners with optional filtering."""
        with self._lock:
            listeners = list(self._listeners.values())

            if project_id:
                listeners = [lis for lis in listeners if lis.project_id == project_id]
            if loadbalancer_id:
                listeners = [lis for lis in listeners if lis.loadbalancer_id == loadbalancer_id]
            if name:
                listeners = [lis for lis in listeners if lis.name == name]
            if protocol:
                listeners = [lis for lis in listeners if lis.protocol.value == protocol]
            if protocol_port:
                listeners = [lis for lis in listeners if lis.protocol_port == protocol_port]

            return listeners

    def update_listener(
        self,
        listener_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        connection_limit: int | None = None,
        default_pool_id: str | None = None,
        default_tls_container_ref: str | None = None,
        sni_container_refs: list[str] | None = None,
        insert_headers: dict[str, str] | None = None,
        timeout_client_data: int | None = None,
        timeout_member_connect: int | None = None,
        timeout_member_data: int | None = None,
        timeout_tcp_inspect: int | None = None,
        allowed_cidrs: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Listener | None:
        """Update a listener."""
        with self._lock:
            listener = self._listeners.get(listener_id)
            if not listener:
                return None
            if project_id is not None and listener.project_id != project_id:
                return None

            if name is not None:
                listener.name = name
            if description is not None:
                listener.description = description
            if admin_state_up is not None:
                listener.admin_state_up = admin_state_up
            if connection_limit is not None:
                listener.connection_limit = connection_limit
            if default_pool_id is not None:
                listener.default_pool_id = default_pool_id
            if default_tls_container_ref is not None:
                listener.default_tls_container_ref = default_tls_container_ref
            if sni_container_refs is not None:
                listener.sni_container_refs = sni_container_refs
            if insert_headers is not None:
                listener.insert_headers = insert_headers
            if timeout_client_data is not None:
                listener.timeout_client_data = timeout_client_data
            if timeout_member_connect is not None:
                listener.timeout_member_connect = timeout_member_connect
            if timeout_member_data is not None:
                listener.timeout_member_data = timeout_member_data
            if timeout_tcp_inspect is not None:
                listener.timeout_tcp_inspect = timeout_tcp_inspect
            if allowed_cidrs is not None:
                listener.allowed_cidrs = allowed_cidrs
            if tags is not None:
                listener.tags = tags

            return listener

    def delete_listener(
        self, listener_id: str, project_id: str | None = None, cascade: bool = False
    ) -> bool:
        """Delete a listener."""
        with self._lock:
            listener = self._listeners.get(listener_id)
            if not listener:
                return False
            if project_id is not None and listener.project_id != project_id:
                return False

            # Remove from load balancer
            lb = self._load_balancers.get(listener.loadbalancer_id)
            if lb:
                lb.listeners = [lis for lis in lb.listeners if lis.id != listener_id]

            # Delete L7 policies if cascade
            if cascade:
                for policy in list(listener.l7policies):
                    self.delete_l7policy(policy.id)

            del self._listeners[listener_id]
            return True

    # Pool operations

    def create_pool(
        self,
        name: str,
        protocol: str,
        lb_algorithm: str,
        project_id: str,
        loadbalancer_id: str | None = None,
        listener_id: str | None = None,
        description: str = "",
        admin_state_up: bool = True,
        session_persistence: dict[str, Any] | None = None,
        tls_enabled: bool = False,
        tags: list[str] | None = None,
    ) -> Pool | None:
        """Create a new pool."""
        with self._lock:
            pool_id = str(uuid4())

            actual_lb_id = loadbalancer_id
            if loadbalancer_id:
                lb = self._load_balancers.get(loadbalancer_id)
                if not lb:
                    return None

            actual_listener_id = listener_id
            if listener_id:
                listener = self._listeners.get(listener_id)
                if not listener:
                    return None
                # Get load balancer from listener
                if listener.loadbalancer_id and not actual_lb_id:
                    actual_lb_id = listener.loadbalancer_id

            pool = Pool(
                id=pool_id,
                name=name,
                description=description,
                admin_state_up=admin_state_up,
                project_id=project_id,
                protocol=PoolProtocol(protocol),
                lb_algorithm=PoolLBAlgorithm(lb_algorithm),
                session_persistence=session_persistence,
                loadbalancer_id=actual_lb_id,
                listener_id=actual_listener_id,
                tls_enabled=tls_enabled,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._pools[pool_id] = pool

            if actual_lb_id:
                lb = self._load_balancers.get(actual_lb_id)
                if lb:
                    lb.pools.append(pool)
            if listener_id:
                listener = self._listeners.get(listener_id)
                if listener:
                    listener.default_pool_id = pool_id

            return pool

    def get_pool(self, pool_id: str, project_id: str | None = None) -> Pool | None:
        """Get a pool by ID."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if pool is None:
                return None
            if project_id is not None and pool.project_id != project_id:
                return None
            return pool

    def list_pools(
        self,
        project_id: str | None = None,
        loadbalancer_id: str | None = None,
        listener_id: str | None = None,
        name: str | None = None,
        protocol: str | None = None,
    ) -> list[Pool]:
        """List pools with optional filtering."""
        with self._lock:
            pools = list(self._pools.values())

            if project_id:
                pools = [p for p in pools if p.project_id == project_id]
            if loadbalancer_id:
                pools = [p for p in pools if p.loadbalancer_id == loadbalancer_id]
            if listener_id:
                pools = [p for p in pools if p.listener_id == listener_id]
            if name:
                pools = [p for p in pools if p.name == name]
            if protocol:
                pools = [p for p in pools if p.protocol.value == protocol]

            return pools

    def update_pool(
        self,
        pool_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        lb_algorithm: str | None = None,
        session_persistence: dict[str, Any] | None = None,
        tls_enabled: bool | None = None,
        tags: list[str] | None = None,
    ) -> Pool | None:
        """Update a pool."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if not pool:
                return None
            if project_id is not None and pool.project_id != project_id:
                return None

            if name is not None:
                pool.name = name
            if description is not None:
                pool.description = description
            if admin_state_up is not None:
                pool.admin_state_up = admin_state_up
            if lb_algorithm is not None:
                pool.lb_algorithm = PoolLBAlgorithm(lb_algorithm)
            if session_persistence is not None:
                pool.session_persistence = session_persistence
            if tls_enabled is not None:
                pool.tls_enabled = tls_enabled
            if tags is not None:
                pool.tags = tags

            return pool

    def delete_pool(self, pool_id: str, project_id: str | None = None) -> bool:
        """Delete a pool."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if not pool:
                return False
            if project_id is not None and pool.project_id != project_id:
                return False

            # Remove from load balancer
            if pool.loadbalancer_id:
                lb = self._load_balancers.get(pool.loadbalancer_id)
                if lb:
                    lb.pools = [p for p in lb.pools if p.id != pool_id]

            # Remove from listener
            if pool.listener_id:
                listener = self._listeners.get(pool.listener_id)
                if listener and listener.default_pool_id == pool_id:
                    listener.default_pool_id = None

            # Delete pool members
            member_keys = [k for k in self._pool_members.keys() if k.startswith(f"{pool_id}:")]
            for key in member_keys:
                del self._pool_members[key]

            # Delete health monitor
            if pool.healthmonitor_id:
                self.delete_health_monitor(pool.healthmonitor_id)

            del self._pools[pool_id]
            return True

    # Pool Member operations

    def create_pool_member(
        self,
        pool_id: str,
        address: str,
        protocol_port: int,
        project_id: str,
        name: str = "",
        weight: int = 1,
        subnet_id: str | None = None,
        admin_state_up: bool = True,
        monitor_address: str | None = None,
        monitor_port: int | None = None,
        backup: bool = False,
        tags: list[str] | None = None,
    ) -> PoolMember | None:
        """Create a new pool member."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if not pool:
                return None

            member_id = str(uuid4())
            member = PoolMember(
                id=member_id,
                name=name,
                address=address,
                protocol_port=protocol_port,
                weight=weight,
                subnet_id=subnet_id or "",
                admin_state_up=admin_state_up,
                project_id=project_id,
                monitor_address=monitor_address,
                monitor_port=monitor_port,
                backup=backup,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._pool_members[f"{pool_id}:{member_id}"] = member
            pool.members.append(member)
            return member

    def get_pool_member(
        self, pool_id: str, member_id: str, project_id: str | None = None
    ) -> PoolMember | None:
        """Get a pool member by ID."""
        with self._lock:
            member = self._pool_members.get(f"{pool_id}:{member_id}")
            if member is None:
                return None
            if project_id is not None and member.project_id != project_id:
                return None
            return member

    def list_pool_members(
        self,
        pool_id: str,
        project_id: str | None = None,
        address: str | None = None,
        protocol_port: int | None = None,
    ) -> list[PoolMember]:
        """List members of a pool."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if not pool:
                return []
            members = list(pool.members)
            if project_id:
                members = [m for m in members if m.project_id == project_id]
            if address:
                members = [m for m in members if m.address == address]
            if protocol_port:
                members = [m for m in members if m.protocol_port == protocol_port]
            return members

    def update_pool_member(
        self,
        pool_id: str,
        member_id: str,
        project_id: str | None = None,
        name: str | None = None,
        weight: int | None = None,
        admin_state_up: bool | None = None,
        monitor_address: str | None = None,
        monitor_port: int | None = None,
        backup: bool | None = None,
        tags: list[str] | None = None,
    ) -> PoolMember | None:
        """Update a pool member."""
        with self._lock:
            member = self._pool_members.get(f"{pool_id}:{member_id}")
            if not member:
                return None
            if project_id is not None and member.project_id != project_id:
                return None

            if name is not None:
                member.name = name
            if weight is not None:
                member.weight = weight
            if admin_state_up is not None:
                member.admin_state_up = admin_state_up
            if monitor_address is not None:
                member.monitor_address = monitor_address
            if monitor_port is not None:
                member.monitor_port = monitor_port
            if backup is not None:
                member.backup = backup
            if tags is not None:
                member.tags = tags

            return member

    def delete_pool_member(
        self, pool_id: str, member_id: str, project_id: str | None = None
    ) -> bool:
        """Delete a pool member."""
        with self._lock:
            key = f"{pool_id}:{member_id}"
            member = self._pool_members.get(key)
            if not member:
                return False
            if project_id is not None and member.project_id != project_id:
                return False

            pool = self._pools.get(pool_id)
            if pool:
                pool.members = [m for m in pool.members if m.id != member_id]

            del self._pool_members[key]
            return True

    # Health Monitor operations

    def create_health_monitor(
        self,
        pool_id: str,
        type: str,
        delay: int,
        timeout: int,
        max_retries: int,
        project_id: str,
        name: str = "",
        max_retries_down: int = 3,
        http_method: str = "GET",
        url_path: str = "/",
        expected_codes: str = "200",
        admin_state_up: bool = True,
        tags: list[str] | None = None,
    ) -> HealthMonitor | None:
        """Create a new health monitor."""
        with self._lock:
            pool = self._pools.get(pool_id)
            if not pool:
                return None

            # Check if pool already has a health monitor
            if pool.healthmonitor_id:
                return None

            monitor_id = str(uuid4())
            monitor = HealthMonitor(
                id=monitor_id,
                name=name,
                type=HealthMonitorType(type),
                delay=delay,
                timeout=timeout,
                max_retries=max_retries,
                max_retries_down=max_retries_down,
                http_method=http_method,
                url_path=url_path,
                expected_codes=expected_codes,
                admin_state_up=admin_state_up,
                project_id=project_id,
                pool_id=pool_id,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._health_monitors[monitor_id] = monitor
            pool.healthmonitor_id = monitor_id
            return monitor

    def get_health_monitor(
        self, monitor_id: str, project_id: str | None = None
    ) -> HealthMonitor | None:
        """Get a health monitor by ID."""
        with self._lock:
            monitor = self._health_monitors.get(monitor_id)
            if monitor is None:
                return None
            if project_id is not None and monitor.project_id != project_id:
                return None
            return monitor

    def list_health_monitors(
        self,
        project_id: str | None = None,
        pool_id: str | None = None,
        type: str | None = None,
    ) -> list[HealthMonitor]:
        """List health monitors with optional filtering."""
        with self._lock:
            monitors = list(self._health_monitors.values())

            if project_id:
                monitors = [m for m in monitors if m.project_id == project_id]
            if pool_id:
                monitors = [m for m in monitors if m.pool_id == pool_id]
            if type:
                monitors = [m for m in monitors if m.type.value == type]

            return monitors

    def update_health_monitor(
        self,
        monitor_id: str,
        project_id: str | None = None,
        name: str | None = None,
        delay: int | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        max_retries_down: int | None = None,
        http_method: str | None = None,
        url_path: str | None = None,
        expected_codes: str | None = None,
        admin_state_up: bool | None = None,
        tags: list[str] | None = None,
    ) -> HealthMonitor | None:
        """Update a health monitor."""
        with self._lock:
            monitor = self._health_monitors.get(monitor_id)
            if not monitor:
                return None
            if project_id is not None and monitor.project_id != project_id:
                return None

            if name is not None:
                monitor.name = name
            if delay is not None:
                monitor.delay = delay
            if timeout is not None:
                monitor.timeout = timeout
            if max_retries is not None:
                monitor.max_retries = max_retries
            if max_retries_down is not None:
                monitor.max_retries_down = max_retries_down
            if http_method is not None:
                monitor.http_method = http_method
            if url_path is not None:
                monitor.url_path = url_path
            if expected_codes is not None:
                monitor.expected_codes = expected_codes
            if admin_state_up is not None:
                monitor.admin_state_up = admin_state_up
            if tags is not None:
                monitor.tags = tags

            return monitor

    def delete_health_monitor(self, monitor_id: str, project_id: str | None = None) -> bool:
        """Delete a health monitor."""
        with self._lock:
            monitor = self._health_monitors.get(monitor_id)
            if not monitor:
                return False
            if project_id is not None and monitor.project_id != project_id:
                return False

            # Remove from pool
            pool = self._pools.get(monitor.pool_id)
            if pool:
                pool.healthmonitor_id = None

            del self._health_monitors[monitor_id]
            return True

    # L7 Policy operations

    def create_l7policy(
        self,
        listener_id: str,
        action: str,
        project_id: str,
        name: str = "",
        description: str = "",
        position: int = 1,
        redirect_pool_id: str | None = None,
        redirect_url: str | None = None,
        redirect_prefix: str | None = None,
        redirect_http_code: int | None = None,
        admin_state_up: bool = True,
        tags: list[str] | None = None,
    ) -> L7Policy | None:
        """Create a new L7 policy."""
        with self._lock:
            listener = self._listeners.get(listener_id)
            if not listener:
                return None

            policy_id = str(uuid4())
            policy = L7Policy(
                id=policy_id,
                name=name,
                description=description,
                admin_state_up=admin_state_up,
                project_id=project_id,
                listener_id=listener_id,
                action=L7PolicyAction(action),
                position=position,
                redirect_pool_id=redirect_pool_id,
                redirect_url=redirect_url,
                redirect_prefix=redirect_prefix,
                redirect_http_code=redirect_http_code,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._l7policies[policy_id] = policy
            listener.l7policies.append(policy)
            return policy

    def get_l7policy(self, policy_id: str, project_id: str | None = None) -> L7Policy | None:
        """Get an L7 policy by ID."""
        with self._lock:
            policy = self._l7policies.get(policy_id)
            if policy is None:
                return None
            if project_id is not None and policy.project_id != project_id:
                return None
            return policy

    def list_l7policies(
        self,
        project_id: str | None = None,
        listener_id: str | None = None,
        action: str | None = None,
    ) -> list[L7Policy]:
        """List L7 policies with optional filtering."""
        with self._lock:
            policies = list(self._l7policies.values())

            if project_id:
                policies = [p for p in policies if p.project_id == project_id]
            if listener_id:
                policies = [p for p in policies if p.listener_id == listener_id]
            if action:
                policies = [p for p in policies if p.action.value == action]

            return policies

    def update_l7policy(
        self,
        policy_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
        action: str | None = None,
        position: int | None = None,
        redirect_pool_id: str | None = None,
        redirect_url: str | None = None,
        redirect_prefix: str | None = None,
        redirect_http_code: int | None = None,
        tags: list[str] | None = None,
    ) -> L7Policy | None:
        """Update an L7 policy."""
        with self._lock:
            policy = self._l7policies.get(policy_id)
            if not policy:
                return None
            if project_id is not None and policy.project_id != project_id:
                return None

            if name is not None:
                policy.name = name
            if description is not None:
                policy.description = description
            if admin_state_up is not None:
                policy.admin_state_up = admin_state_up
            if action is not None:
                policy.action = L7PolicyAction(action)
            if position is not None:
                policy.position = position
            if redirect_pool_id is not None:
                policy.redirect_pool_id = redirect_pool_id
            if redirect_url is not None:
                policy.redirect_url = redirect_url
            if redirect_prefix is not None:
                policy.redirect_prefix = redirect_prefix
            if redirect_http_code is not None:
                policy.redirect_http_code = redirect_http_code
            if tags is not None:
                policy.tags = tags

            return policy

    def delete_l7policy(self, policy_id: str, project_id: str | None = None) -> bool:
        """Delete an L7 policy."""
        with self._lock:
            policy = self._l7policies.get(policy_id)
            if not policy:
                return False
            if project_id is not None and policy.project_id != project_id:
                return False

            # Remove from listener
            listener = self._listeners.get(policy.listener_id)
            if listener:
                listener.l7policies = [p for p in listener.l7policies if p.id != policy_id]

            # Delete associated rules
            rule_keys = [k for k in self._l7rules.keys() if k.startswith(f"{policy_id}:")]
            for key in rule_keys:
                del self._l7rules[key]

            del self._l7policies[policy_id]
            return True

    # L7 Rule operations

    def create_l7rule(
        self,
        l7policy_id: str,
        type: str,
        compare_type: str,
        value: str,
        project_id: str,
        key: str | None = None,
        invert: bool = False,
        admin_state_up: bool = True,
        tags: list[str] | None = None,
    ) -> L7Rule | None:
        """Create a new L7 rule."""
        with self._lock:
            policy = self._l7policies.get(l7policy_id)
            if not policy:
                return None

            rule_id = str(uuid4())
            rule = L7Rule(
                id=rule_id,
                type=L7RuleType(type),
                compare_type=L7RuleCompareType(compare_type),
                value=value,
                key=key,
                invert=invert,
                admin_state_up=admin_state_up,
                project_id=project_id,
                provisioning_status=LoadBalancerProvisioningStatus.ACTIVE,
                operating_status=LoadBalancerOperatingStatus.ONLINE,
                tags=tags or [],
            )
            self._l7rules[f"{l7policy_id}:{rule_id}"] = rule
            policy.rules.append(rule)
            return rule

    def get_l7rule(
        self, l7policy_id: str, rule_id: str, project_id: str | None = None
    ) -> L7Rule | None:
        """Get an L7 rule by ID."""
        with self._lock:
            rule = self._l7rules.get(f"{l7policy_id}:{rule_id}")
            if rule is None:
                return None
            if project_id is not None and rule.project_id != project_id:
                return None
            return rule

    def list_l7rules(
        self,
        l7policy_id: str,
        project_id: str | None = None,
        type: str | None = None,
    ) -> list[L7Rule]:
        """List rules for an L7 policy."""
        with self._lock:
            policy = self._l7policies.get(l7policy_id)
            if not policy:
                return []
            rules = list(policy.rules)
            if project_id:
                rules = [r for r in rules if r.project_id == project_id]
            if type:
                rules = [r for r in rules if r.type.value == type]
            return rules

    def update_l7rule(
        self,
        l7policy_id: str,
        rule_id: str,
        project_id: str | None = None,
        type: str | None = None,
        compare_type: str | None = None,
        value: str | None = None,
        key: str | None = None,
        invert: bool | None = None,
        admin_state_up: bool | None = None,
        tags: list[str] | None = None,
    ) -> L7Rule | None:
        """Update an L7 rule."""
        with self._lock:
            rule = self._l7rules.get(f"{l7policy_id}:{rule_id}")
            if not rule:
                return None
            if project_id is not None and rule.project_id != project_id:
                return None

            if type is not None:
                rule.type = L7RuleType(type)
            if compare_type is not None:
                rule.compare_type = L7RuleCompareType(compare_type)
            if value is not None:
                rule.value = value
            if key is not None:
                rule.key = key
            if invert is not None:
                rule.invert = invert
            if admin_state_up is not None:
                rule.admin_state_up = admin_state_up
            if tags is not None:
                rule.tags = tags

            return rule

    def delete_l7rule(self, l7policy_id: str, rule_id: str, project_id: str | None = None) -> bool:
        """Delete an L7 rule."""
        with self._lock:
            key = f"{l7policy_id}:{rule_id}"
            rule = self._l7rules.get(key)
            if not rule:
                return False
            if project_id is not None and rule.project_id != project_id:
                return False

            policy = self._l7policies.get(l7policy_id)
            if policy:
                policy.rules = [r for r in policy.rules if r.id != rule_id]

            del self._l7rules[key]
            return True

    def reset_octavia(self) -> None:
        """Reset all Octavia data to defaults."""
        with self._lock:
            self._load_balancers.clear()
            self._listeners.clear()
            self._pools.clear()
            self._pool_members.clear()
            self._health_monitors.clear()
            self._l7policies.clear()
            self._l7rules.clear()
            self._next_lb_vip = 1


# Global database instance
db = Database()
