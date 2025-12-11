"""In-memory database for OpenStack emulator."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from emulator.core.models import (
    Credential,
    Domain,
    Endpoint,
    Flavor,
    Group,
    Image,
    Keypair,
    PowerState,
    Project,
    Region,
    Role,
    RoleAssignment,
    Server,
    ServerStatus,
    Service,
    Token,
    User,
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

        # Initialize with default data
        self._init_default_flavors()
        self._init_default_images()
        self._init_default_keystone_data()

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
        """Create default images for testing."""
        default_images = [
            Image(
                id=str(uuid4()),
                name="cirros-0.6.2-x86_64",
                status="ACTIVE",
                min_disk=1,
                min_ram=128,
                size=21430272,
            ),
            Image(
                id=str(uuid4()),
                name="ubuntu-22.04-server",
                status="ACTIVE",
                min_disk=8,
                min_ram=512,
                size=2361393152,
            ),
            Image(
                id=str(uuid4()),
                name="debian-12-genericcloud",
                status="ACTIVE",
                min_disk=2,
                min_ram=512,
                size=261816320,
            ),
        ]
        for image in default_images:
            self._images[image.id] = image

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

        # Store service IDs for catalog generation
        self._service_ids = {
            "identity": identity_service.id,
            "compute": compute_service.id,
            "image": image_service.id,
        }

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
        """Generate a service catalog for tokens."""
        return [
            {
                "type": "compute",
                "name": "nova",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{base_url}/v2.1",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{base_url}/v2.1",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{base_url}/v2.1",
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
                        "url": f"{base_url}/v3",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{base_url}/v3",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{base_url}/v3",
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


# Global database instance
db = Database()
