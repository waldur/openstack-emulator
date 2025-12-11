"""In-memory database for OpenStack emulator."""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from emulator.core.models import (
    Flavor,
    Image,
    Keypair,
    PowerState,
    Server,
    ServerStatus,
    Token,
)


class Database:
    """In-memory database for storing OpenStack resources."""

    def __init__(self, persist_path: str | None = None) -> None:
        """Initialize the database with optional persistence."""
        self._lock = threading.RLock()
        self.persist_path = persist_path

        # Storage dictionaries
        self._servers: dict[str, Server] = {}
        self._flavors: dict[str, Flavor] = {}
        self._images: dict[str, Image] = {}
        self._keypairs: dict[str, Keypair] = {}  # key: user_id:name
        self._tokens: dict[str, Token] = {}

        # Initialize with default data
        self._init_default_flavors()
        self._init_default_images()
        self._init_default_users()

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

    def _init_default_users(self) -> None:
        """Initialize default admin user and project."""
        self._default_user_id = str(uuid4())
        self._default_user_name = "admin"
        self._default_project_id = str(uuid4())
        self._default_project_name = "admin"

    # Token operations
    def create_token(
        self,
        user_name: str = "admin",
        project_name: str = "admin",
        base_url: str = "http://localhost:8774",
    ) -> Token:
        """Create a new authentication token."""
        with self._lock:
            token = Token(
                id=str(uuid4()),
                user_id=self._default_user_id,
                user_name=user_name,
                project_id=self._default_project_id,
                project_name=project_name,
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


# Global database instance
db = Database()
