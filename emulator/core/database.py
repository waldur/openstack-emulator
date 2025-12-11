"""In-memory database for OpenStack emulator."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from emulator.core.models import (
    ContainerFormat,
    Credential,
    DiskFormat,
    Domain,
    Endpoint,
    Flavor,
    GlanceImage,
    Group,
    Image,
    ImageMember,
    ImageStatus,
    ImageVisibility,
    Keypair,
    PowerState,
    Project,
    QosSpec,
    Region,
    Role,
    RoleAssignment,
    Server,
    ServerStatus,
    Service,
    Snapshot,
    SnapshotStatus,
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

        # Initialize with default data
        self._init_default_flavors()
        self._init_default_images()
        self._init_default_glance_images()
        self._init_default_keystone_data()
        self._init_default_volume_types()

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

    def list_flavors(
        self, is_public: bool | None = None, limit: int | None = None
    ) -> list[Flavor]:
        """List flavors with optional filtering."""
        with self._lock:
            flavors = list(self._flavors.values())

            if is_public is not None:
                flavors = [f for f in flavors if f.is_public == is_public]

            # Sort by ID (numeric)
            flavors.sort(key=lambda f: int(f.id) if f.id.isdigit() else f.id)

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
                "servers": {
                    k: self._server_to_dict(v) for k, v in self._servers.items()
                },
                "flavors": {
                    k: self._flavor_to_dict(v) for k, v in self._flavors.items()
                },
                "images": {k: self._image_to_dict(v) for k, v in self._images.items()},
                "keypairs": {
                    k: self._keypair_to_dict(v) for k, v in self._keypairs.items()
                },
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
                data = json.load(f)

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
                if ra.role_id == role_id and ra.group_id == group_id and ra.project_id == project_id:
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

    def revoke_role_from_user_on_project(
        self, role_id: str, user_id: str, project_id: str
    ) -> bool:
        """Revoke a role from a user on a project."""
        with self._lock:
            for i, ra in enumerate(self._role_assignments):
                if ra.role_id == role_id and ra.user_id == user_id and ra.project_id == project_id:
                    del self._role_assignments[i]
                    return True
            return False

    def revoke_role_from_user_on_domain(
        self, role_id: str, user_id: str, domain_id: str
    ) -> bool:
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
                if ra.role_id == role_id and ra.group_id == group_id and ra.project_id == project_id:
                    del self._role_assignments[i]
                    return True
            return False

    def revoke_role_from_group_on_domain(
        self, role_id: str, group_id: str, domain_id: str
    ) -> bool:
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

    def get_volume(self, volume_id: str) -> Volume | None:
        """Get a volume by ID."""
        with self._lock:
            return self._volumes.get(volume_id)

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
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Volume | None:
        """Update a volume."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if volume:
                if name is not None:
                    volume.name = name
                if description is not None:
                    volume.description = description
                if metadata is not None:
                    volume.metadata = metadata
                volume.updated_at = datetime.utcnow()
            return volume

    def delete_volume(self, volume_id: str) -> bool:
        """Delete a volume."""
        with self._lock:
            if volume_id in self._volumes:
                volume = self._volumes[volume_id]
                # Check if volume can be deleted
                if volume.status == VolumeStatus.IN_USE:
                    return False
                if volume.attachments:
                    return False
                del self._volumes[volume_id]
                return True
            return False

    def extend_volume(self, volume_id: str, new_size: int) -> Volume | None:
        """Extend a volume to a new size."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if volume and new_size > volume.size:
                if volume.status == VolumeStatus.AVAILABLE:
                    volume.size = new_size
                    volume.updated_at = datetime.utcnow()
                    return volume
            return None

    def attach_volume(
        self,
        volume_id: str,
        server_id: str,
        device: str = "/dev/vdb",
        host_name: str = "compute-host-1",
    ) -> VolumeAttachment | None:
        """Attach a volume to a server."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
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

    def detach_volume(self, volume_id: str, attachment_id: str) -> bool:
        """Detach a volume from a server."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if not volume:
                return False

            for i, attachment in enumerate(volume.attachments):
                if attachment.id == attachment_id or attachment.attachment_id == attachment_id:
                    del volume.attachments[i]
                    if not volume.attachments:
                        volume.status = VolumeStatus.AVAILABLE
                    volume.updated_at = datetime.utcnow()
                    return True
            return False

    def set_volume_bootable(self, volume_id: str, bootable: bool) -> Volume | None:
        """Set volume bootable flag."""
        with self._lock:
            volume = self._volumes.get(volume_id)
            if volume:
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

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        """Get a snapshot by ID."""
        with self._lock:
            return self._snapshots.get(snapshot_id)

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
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Snapshot | None:
        """Update a snapshot."""
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot:
                if name is not None:
                    snapshot.name = name
                if description is not None:
                    snapshot.description = description
                if metadata is not None:
                    snapshot.metadata = metadata
                snapshot.updated_at = datetime.utcnow()
            return snapshot

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        with self._lock:
            if snapshot_id in self._snapshots:
                del self._snapshots[snapshot_id]
                return True
            return False

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

    def delete_volume_type_extra_spec(
        self, volume_type_id: str, key: str
    ) -> bool:
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

    def associate_qos_spec_with_type(
        self, qos_id: str, volume_type_id: str
    ) -> bool:
        """Associate a QoS spec with a volume type."""
        with self._lock:
            qos = self._qos_specs.get(qos_id)
            vtype = self._volume_types.get(volume_type_id)
            if qos and vtype:
                vtype.qos_specs_id = qos_id
                return True
            return False

    def disassociate_qos_spec_from_type(
        self, qos_id: str, volume_type_id: str
    ) -> bool:
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

    def update_image_member(
        self, image_id: str, member_id: str, status: str
    ) -> ImageMember | None:
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


# Global database instance
db = Database()
