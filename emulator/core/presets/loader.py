"""Preset loader for OpenStack emulator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from emulator.core.models import ContainerFormat, DiskFormat, ImageVisibility
from emulator.core.presets.schema import (
    CinderConfig,
    FloatingIPConfig,
    GlanceConfig,
    KeystoneConfig,
    ListenerConfig,
    LoadBalancerConfig,
    NetworkConfig,
    NeutronConfig,
    NovaConfig,
    OctaviaConfig,
    PoolConfig,
    PresetConfig,
    ProjectConfig,
    RouterConfig,
    SecurityGroupConfig,
    ServerConfig,
    SubnetConfig,
    VolumeConfig,
)

if TYPE_CHECKING:
    from emulator.core.database import Database

logger = logging.getLogger(__name__)


@dataclass
class PresetResult:
    """Result of loading a preset."""

    success: bool
    preset_name: str
    resources_created: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def resource_count(self) -> int:
        """Total number of resources created."""
        return sum(self.resources_created.values())


class PresetLoader:
    """Loads and applies resource presets to the database."""

    # Built-in preset directory
    BUILTIN_PRESETS_DIR = Path(__file__).parent.parent.parent / "presets"

    def __init__(self, db: Database) -> None:
        """Initialize the preset loader.

        Args:
            db: The database instance to load presets into.
        """
        self.db = db
        # Maps resource names to IDs for cross-referencing
        self._resource_map: dict[str, dict[str, str]] = {
            "projects": {},
            "users": {},
            "networks": {},
            "subnets": {},
            "routers": {},
            "security_groups": {},
            "servers": {},
            "volumes": {},
            "images": {},
            "load_balancers": {},
            "listeners": {},
            "pools": {},
        }

    def list_available_presets(self) -> list[dict[str, str]]:
        """List all available built-in presets.

        Returns:
            List of preset info dicts with 'name' and 'description' keys.
        """
        presets = []
        if self.BUILTIN_PRESETS_DIR.exists():
            for preset_file in self.BUILTIN_PRESETS_DIR.glob("*.yaml"):
                try:
                    with open(preset_file) as f:
                        data = yaml.safe_load(f)
                        presets.append(
                            {
                                "name": data.get("name", preset_file.stem),
                                "description": data.get("description", ""),
                                "file": preset_file.name,
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to read preset {preset_file}: {e}")
        return presets

    def load_preset_by_name(self, name: str) -> PresetResult:
        """Load a built-in preset by name.

        Args:
            name: The preset name (without .yaml extension).

        Returns:
            PresetResult with success status and resource counts.
        """
        preset_path = self.BUILTIN_PRESETS_DIR / f"{name}.yaml"
        if not preset_path.exists():
            return PresetResult(
                success=False,
                preset_name=name,
                errors=[f"Preset '{name}' not found"],
            )
        return self.load_preset(preset_path)

    def load_preset(self, preset_path: str | Path) -> PresetResult:
        """Load a preset from a YAML file.

        Args:
            preset_path: Path to the preset YAML file.

        Returns:
            PresetResult with success status and resource counts.
        """
        preset_path = Path(preset_path)
        if not preset_path.exists():
            return PresetResult(
                success=False,
                preset_name=str(preset_path),
                errors=[f"File not found: {preset_path}"],
            )

        try:
            with open(preset_path) as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return PresetResult(
                success=False,
                preset_name=str(preset_path),
                errors=[f"YAML parse error: {e}"],
            )

        try:
            config = PresetConfig(**raw_config)
        except Exception as e:
            return PresetResult(
                success=False,
                preset_name=str(preset_path),
                errors=[f"Validation error: {e}"],
            )

        return self._apply_preset(config)

    def load_preset_from_dict(self, config_dict: dict[str, Any]) -> PresetResult:
        """Load a preset from a dictionary.

        Args:
            config_dict: The preset configuration as a dictionary.

        Returns:
            PresetResult with success status and resource counts.
        """
        try:
            config = PresetConfig(**config_dict)
        except Exception as e:
            return PresetResult(
                success=False,
                preset_name=config_dict.get("name", "unknown"),
                errors=[f"Validation error: {e}"],
            )

        return self._apply_preset(config)

    def _apply_preset(self, config: PresetConfig) -> PresetResult:
        """Apply a validated preset configuration.

        Args:
            config: The validated preset configuration.

        Returns:
            PresetResult with success status and resource counts.
        """
        result = PresetResult(success=True, preset_name=config.name)

        # Reset resource map
        for key in self._resource_map:
            self._resource_map[key] = {}

        # Build initial resource map from existing resources
        self._build_existing_resource_map()

        # Apply resources in dependency order
        try:
            # 1. Keystone resources (projects, users, roles)
            self._apply_keystone(config.keystone, result)

            # 2. Glance images
            self._apply_glance(config.glance, result)

            # 3. Neutron resources (networks, subnets, security groups, routers)
            self._apply_neutron(config.neutron, result)

            # 4. Nova resources (keypairs, servers)
            self._apply_nova(config.nova, result)

            # 5. Cinder resources (volumes, snapshots)
            self._apply_cinder(config.cinder, result)

            # 6. Octavia resources (load balancers, listeners, pools)
            self._apply_octavia(config.octavia, result)

        except Exception as e:
            result.success = False
            result.errors.append(f"Unexpected error: {e}")
            logger.exception("Error applying preset")

        return result

    def _build_existing_resource_map(self) -> None:
        """Build resource map from existing database resources."""
        # Projects
        for project in self.db.list_projects():
            self._resource_map["projects"][project.name] = project.id

        # Users
        for user in self.db.list_users():
            self._resource_map["users"][user.name] = user.id

        # Networks
        for network in self.db.list_networks():
            self._resource_map["networks"][network.name] = network.id

        # Subnets
        for subnet in self.db.list_subnets():
            self._resource_map["subnets"][subnet.name] = subnet.id

        # Security groups
        for sg in self.db.list_security_groups():
            self._resource_map["security_groups"][sg.name] = sg.id

        # Routers
        for router in self.db.list_routers():
            self._resource_map["routers"][router.name] = router.id

        # Servers
        for server in self.db.list_servers():
            self._resource_map["servers"][server.name] = server.id

        # Volumes
        for volume in self.db.list_volumes():
            self._resource_map["volumes"][volume.name] = volume.id

        # Images
        for image in self.db.list_glance_images():
            self._resource_map["images"][image.name] = image.id

        # Load balancers
        for lb in self.db.list_load_balancers():
            self._resource_map["load_balancers"][lb.name] = lb.id

    def _resolve_project_id(self, project_name: str | None) -> str:
        """Resolve a project name to ID.

        Args:
            project_name: The project name or None for default.

        Returns:
            The project ID.
        """
        if not project_name:
            return self.db._default_project_id

        # Check resource map first
        if project_name in self._resource_map["projects"]:
            return self._resource_map["projects"][project_name]

        # Try to find by name in database
        project = self.db.get_project_by_name(project_name)
        if project:
            self._resource_map["projects"][project_name] = project.id
            return project.id

        return self.db._default_project_id

    def _resolve_user_id(self, user_name: str | None) -> str:
        """Resolve a user name to ID."""
        if not user_name:
            return self.db._default_user_id

        if user_name in self._resource_map["users"]:
            return self._resource_map["users"][user_name]

        user = self.db.get_user_by_name(user_name)
        if user:
            self._resource_map["users"][user_name] = user.id
            return user.id

        return self.db._default_user_id

    def _resolve_network_id(self, network_name: str) -> str | None:
        """Resolve a network name to ID."""
        if network_name in self._resource_map["networks"]:
            return self._resource_map["networks"][network_name]

        networks = self.db.list_networks(name=network_name)
        if networks:
            self._resource_map["networks"][network_name] = networks[0].id
            return networks[0].id

        return None

    def _resolve_subnet_id(self, subnet_name: str) -> str | None:
        """Resolve a subnet name to ID."""
        if subnet_name in self._resource_map["subnets"]:
            return self._resource_map["subnets"][subnet_name]

        subnets = self.db.list_subnets(name=subnet_name)
        if subnets:
            self._resource_map["subnets"][subnet_name] = subnets[0].id
            return subnets[0].id

        return None

    def _resolve_security_group_id(self, sg_name: str, project_id: str) -> str | None:
        """Resolve a security group name to ID."""
        if sg_name in self._resource_map["security_groups"]:
            return self._resource_map["security_groups"][sg_name]

        sgs = self.db.list_security_groups(project_id=project_id)
        for sg in sgs:
            if sg.name == sg_name:
                self._resource_map["security_groups"][sg_name] = sg.id
                return sg.id

        return None

    def _resolve_server_id(self, server_name: str) -> str | None:
        """Resolve a server name to ID."""
        if server_name in self._resource_map["servers"]:
            return self._resource_map["servers"][server_name]

        servers = self.db.list_servers(name=server_name)
        if servers:
            self._resource_map["servers"][server_name] = servers[0].id
            return servers[0].id

        return None

    def _resolve_image_id(self, image_name: str) -> str | None:
        """Resolve an image name to ID."""
        if image_name in self._resource_map["images"]:
            return self._resource_map["images"][image_name]

        images = self.db.list_glance_images(name=image_name)
        if images:
            self._resource_map["images"][image_name] = images[0].id
            return images[0].id

        return None

    def _resolve_flavor_id(self, flavor_name: str) -> str | None:
        """Resolve a flavor name to ID."""
        flavors = self.db.list_flavors()
        for flv in flavors:
            if flv.name == flavor_name:
                return flv.id
        # Try by ID
        flv_by_id = self.db.get_flavor(flavor_name)
        if flv_by_id:
            return flv_by_id.id
        return None

    def _resolve_volume_id(self, volume_name: str) -> str | None:
        """Resolve a volume name to ID."""
        if volume_name in self._resource_map["volumes"]:
            return self._resource_map["volumes"][volume_name]

        volumes = self.db.list_volumes()
        for volume in volumes:
            if volume.name == volume_name:
                self._resource_map["volumes"][volume_name] = volume.id
                return volume.id

        return None

    def _apply_keystone(self, config: KeystoneConfig, result: PresetResult) -> None:
        """Apply Keystone resources."""
        count = 0

        for project_cfg in config.projects:
            project = self._create_project(project_cfg, result)
            if project:
                count += 1
                # Create users for this project
                for user_cfg in project_cfg.users:
                    user = self._create_user(user_cfg, project.id, result)
                    if user:
                        count += 1

        result.resources_created["keystone"] = count

    def _create_project(self, cfg: ProjectConfig, result: PresetResult) -> Any | None:
        """Create a project from config."""
        # Skip if already exists
        if cfg.name in self._resource_map["projects"]:
            logger.debug(f"Project '{cfg.name}' already exists, skipping")
            return self.db.get_project(self._resource_map["projects"][cfg.name])

        try:
            project = self.db.create_project(
                name=cfg.name,
                domain_id=cfg.domain,
                description=cfg.description,
            )
            self._resource_map["projects"][cfg.name] = project.id
            logger.info(f"Created project: {cfg.name} ({project.id})")
            return project
        except Exception as e:
            result.errors.append(f"Failed to create project '{cfg.name}': {e}")
            return None

    def _create_user(self, cfg: Any, project_id: str, result: PresetResult) -> Any | None:
        """Create a user from config."""
        # Skip if already exists
        if cfg.name in self._resource_map["users"]:
            logger.debug(f"User '{cfg.name}' already exists, skipping")
            return self.db.get_user(self._resource_map["users"][cfg.name])

        try:
            user = self.db.create_user(
                name=cfg.name,
                password=cfg.password,
                email=cfg.email or f"{cfg.name}@example.com",
                default_project_id=project_id,
            )
            self._resource_map["users"][cfg.name] = user.id
            logger.info(f"Created user: {cfg.name} ({user.id})")

            # Assign roles
            for role_name in cfg.roles:
                role = self.db.get_role_by_name(role_name)
                if role:
                    self.db.assign_role_to_user_on_project(role.id, user.id, project_id)
                    logger.debug(f"Assigned role '{role_name}' to user '{cfg.name}'")

            return user
        except Exception as e:
            result.errors.append(f"Failed to create user '{cfg.name}': {e}")
            return None

    def _apply_glance(self, config: GlanceConfig, result: PresetResult) -> None:
        """Apply Glance resources."""
        count = 0

        for image_cfg in config.images:
            if image_cfg.name in self._resource_map["images"]:
                logger.debug(f"Image '{image_cfg.name}' already exists, skipping")
                continue

            try:
                # Convert string values to enums
                visibility = ImageVisibility(image_cfg.visibility)
                container_format = (
                    ContainerFormat(image_cfg.container_format)
                    if image_cfg.container_format
                    else None
                )
                disk_format = DiskFormat(image_cfg.disk_format) if image_cfg.disk_format else None

                image = self.db.create_glance_image(
                    name=image_cfg.name,
                    owner="admin",
                    visibility=visibility,
                    container_format=container_format,
                    disk_format=disk_format,
                    min_disk=image_cfg.min_disk,
                    min_ram=image_cfg.min_ram,
                    architecture=image_cfg.architecture,
                    os_distro=image_cfg.os_distro,
                    os_version=image_cfg.os_version,
                )
                self._resource_map["images"][image_cfg.name] = image.id
                count += 1
                logger.info(f"Created image: {image_cfg.name} ({image.id})")
            except Exception as e:
                result.errors.append(f"Failed to create image '{image_cfg.name}': {e}")

        result.resources_created["glance"] = count

    def _apply_neutron(self, config: NeutronConfig, result: PresetResult) -> None:
        """Apply Neutron resources."""
        count = 0

        # 1. Create networks and subnets
        for network_cfg in config.networks:
            network, subnet_count = self._create_network(network_cfg, result)
            if network:
                count += 1 + subnet_count

        # 2. Create security groups
        for sg_cfg in config.security_groups:
            sg = self._create_security_group(sg_cfg, result)
            if sg:
                count += 1

        # 3. Create routers and attach interfaces
        for router_cfg in config.routers:
            router = self._create_router(router_cfg, result)
            if router:
                count += 1

        # 4. Create floating IPs
        for fip_cfg in config.floating_ips:
            fip = self._create_floating_ip(fip_cfg, result)
            if fip:
                count += 1

        result.resources_created["neutron"] = count

    def _create_network(self, cfg: NetworkConfig, result: PresetResult) -> tuple[Any | None, int]:
        """Create a network and its subnets."""
        # Skip if already exists
        if cfg.name in self._resource_map["networks"]:
            logger.debug(f"Network '{cfg.name}' already exists, skipping")
            network_id = self._resource_map["networks"][cfg.name]
            return self.db.get_network(network_id), 0

        project_id = self._resolve_project_id(cfg.project)

        try:
            network = self.db.create_network(
                name=cfg.name,
                project_id=project_id,
                shared=cfg.shared,
                external=cfg.external,
            )
            self._resource_map["networks"][cfg.name] = network.id
            logger.info(f"Created network: {cfg.name} ({network.id})")

            # Create subnets
            subnet_count = 0
            for subnet_cfg in cfg.subnets:
                subnet = self._create_subnet(subnet_cfg, network.id, project_id, result)
                if subnet:
                    subnet_count += 1

            return network, subnet_count
        except Exception as e:
            result.errors.append(f"Failed to create network '{cfg.name}': {e}")
            return None, 0

    def _create_subnet(
        self,
        cfg: SubnetConfig,
        network_id: str,
        project_id: str,
        result: PresetResult,
    ) -> Any | None:
        """Create a subnet."""
        if cfg.name in self._resource_map["subnets"]:
            logger.debug(f"Subnet '{cfg.name}' already exists, skipping")
            return self.db.get_subnet(self._resource_map["subnets"][cfg.name])

        try:
            allocation_pools = None
            if cfg.allocation_pools:
                allocation_pools = cfg.allocation_pools

            subnet = self.db.create_subnet(
                network_id=network_id,
                cidr=cfg.cidr,
                project_id=project_id,
                name=cfg.name,
                gateway_ip=cfg.gateway,
                allocation_pools=allocation_pools,
                dns_nameservers=cfg.dns_nameservers if cfg.dns_nameservers else None,
                enable_dhcp=cfg.enable_dhcp,
            )
            if subnet:
                self._resource_map["subnets"][cfg.name] = subnet.id
                logger.info(f"Created subnet: {cfg.name} ({subnet.id})")
            return subnet
        except Exception as e:
            result.errors.append(f"Failed to create subnet '{cfg.name}': {e}")
            return None

    def _create_security_group(self, cfg: SecurityGroupConfig, result: PresetResult) -> Any | None:
        """Create a security group with rules."""
        project_id = self._resolve_project_id(cfg.project)

        # Check if exists
        existing_id = self._resolve_security_group_id(cfg.name, project_id)
        if existing_id:
            logger.debug(f"Security group '{cfg.name}' already exists, skipping")
            return self.db.get_security_group(existing_id)

        try:
            sg = self.db.create_security_group(
                name=cfg.name,
                project_id=project_id,
                description=cfg.description,
            )
            self._resource_map["security_groups"][cfg.name] = sg.id
            logger.info(f"Created security group: {cfg.name} ({sg.id})")

            # Create rules
            for rule_cfg in cfg.rules:
                self.db.create_security_group_rule(
                    security_group_id=sg.id,
                    project_id=project_id,
                    direction=rule_cfg.direction,
                    protocol=rule_cfg.protocol,
                    port_range_min=rule_cfg.port_range_min,
                    port_range_max=rule_cfg.port_range_max,
                    remote_ip_prefix=rule_cfg.remote_ip_prefix,
                    remote_group_id=(
                        self._resolve_security_group_id(rule_cfg.remote_group, project_id)
                        if rule_cfg.remote_group
                        else None
                    ),
                    ethertype=rule_cfg.ethertype,
                )

            return sg
        except Exception as e:
            result.errors.append(f"Failed to create security group '{cfg.name}': {e}")
            return None

    def _create_router(self, cfg: RouterConfig, result: PresetResult) -> Any | None:
        """Create a router and attach interfaces."""
        if cfg.name in self._resource_map["routers"]:
            logger.debug(f"Router '{cfg.name}' already exists, skipping")
            return self.db.get_router(self._resource_map["routers"][cfg.name])

        project_id = self._resolve_project_id(cfg.project)

        try:
            external_gateway_info = None
            if cfg.external_network:
                ext_network_id = self._resolve_network_id(cfg.external_network)
                if ext_network_id:
                    external_gateway_info = {"network_id": ext_network_id}

            router = self.db.create_router(
                name=cfg.name,
                project_id=project_id,
                external_gateway_info=external_gateway_info,
            )
            self._resource_map["routers"][cfg.name] = router.id
            logger.info(f"Created router: {cfg.name} ({router.id})")

            # Attach interfaces
            for interface_cfg in cfg.interfaces:
                subnet_id = self._resolve_subnet_id(interface_cfg.subnet)
                if subnet_id:
                    self.db.add_router_interface(
                        router_id=router.id,
                        project_id=project_id,
                        subnet_id=subnet_id,
                    )
                    logger.debug(
                        f"Added interface to router '{cfg.name}': subnet={interface_cfg.subnet}"
                    )

            return router
        except Exception as e:
            result.errors.append(f"Failed to create router '{cfg.name}': {e}")
            return None

    def _create_floating_ip(self, cfg: FloatingIPConfig, result: PresetResult) -> Any | None:
        """Create a floating IP."""
        project_id = self._resolve_project_id(cfg.project)
        network_id = self._resolve_network_id(cfg.floating_network)

        if not network_id:
            result.errors.append(f"Floating IP: network '{cfg.floating_network}' not found")
            return None

        try:
            fip = self.db.create_floating_ip(
                floating_network_id=network_id,
                project_id=project_id,
            )
            if not fip:
                result.errors.append("Failed to create floating IP: creation returned None")
                return None

            logger.info(f"Created floating IP: {fip.floating_ip_address} ({fip.id})")

            # Associate with server if specified
            if cfg.server:
                server_id = self._resolve_server_id(cfg.server)
                if server_id:
                    server = self.db.get_server(server_id)
                    if server and server.addresses:
                        # Get first port from server
                        for net_name, addrs in server.addresses.items():
                            if addrs:
                                # Find the port
                                ports = self.db.list_ports(device_id=server_id)
                                if ports:
                                    self.db.update_floating_ip(
                                        fip.id,
                                        project_id=project_id,
                                        port_id=ports[0].id,
                                    )
                                    break

            return fip
        except Exception as e:
            result.errors.append(f"Failed to create floating IP: {e}")
            return None

    def _apply_nova(self, config: NovaConfig, result: PresetResult) -> None:
        """Apply Nova resources."""
        count = 0

        # Create keypairs
        for kp_cfg in config.keypairs:
            if self._create_keypair(kp_cfg, result):
                count += 1

        # Create servers
        for server_cfg in config.servers:
            server = self._create_server(server_cfg, result)
            if server:
                count += 1

        result.resources_created["nova"] = count

    def _create_keypair(self, cfg: Any, result: PresetResult) -> Any | None:
        """Create a keypair."""
        user_id = self._resolve_user_id(cfg.user)

        try:
            keypair = self.db.create_keypair(
                name=cfg.name,
                user_id=user_id,
                public_key=cfg.public_key,
            )
            logger.info(f"Created keypair: {cfg.name}")
            return keypair
        except Exception as e:
            result.errors.append(f"Failed to create keypair '{cfg.name}': {e}")
            return None

    def _create_server(self, cfg: ServerConfig, result: PresetResult) -> Any | None:
        """Create a server."""
        if cfg.name in self._resource_map["servers"]:
            logger.debug(f"Server '{cfg.name}' already exists, skipping")
            return self.db.get_server(self._resource_map["servers"][cfg.name])

        project_id = self._resolve_project_id(cfg.project)

        # Resolve flavor
        flavor_id = self._resolve_flavor_id(cfg.flavor)
        if not flavor_id:
            result.errors.append(f"Server '{cfg.name}': flavor '{cfg.flavor}' not found")
            return None

        # Resolve image
        image_id = self._resolve_image_id(cfg.image)
        if not image_id:
            result.errors.append(f"Server '{cfg.name}': image '{cfg.image}' not found")
            return None

        # Build networks list
        networks = []
        if cfg.network:
            network_id = self._resolve_network_id(cfg.network)
            if network_id:
                networks.append({"uuid": network_id})
        for net_name in cfg.networks:
            network_id = self._resolve_network_id(net_name)
            if network_id:
                networks.append({"uuid": network_id})

        # Build security groups list
        security_groups = []
        for sg_name in cfg.security_groups:
            sg_id = self._resolve_security_group_id(sg_name, project_id)
            if sg_id:
                security_groups.append({"name": sg_name})
        if not security_groups:
            security_groups = [{"name": "default"}]

        try:
            server = self.db.create_server(
                name=cfg.name,
                flavor_id=flavor_id,
                image_id=image_id,
                tenant_id=project_id,
                key_name=cfg.key_name,
                metadata=cfg.metadata,
                security_groups=security_groups,
                availability_zone=cfg.availability_zone or "nova",
                networks=networks if networks else None,
            )
            self._resource_map["servers"][cfg.name] = server.id
            logger.info(f"Created server: {cfg.name} ({server.id})")
            return server
        except Exception as e:
            result.errors.append(f"Failed to create server '{cfg.name}': {e}")
            return None

    def _apply_cinder(self, config: CinderConfig, result: PresetResult) -> None:
        """Apply Cinder resources."""
        count = 0

        # Create volumes
        for volume_cfg in config.volumes:
            volume = self._create_volume(volume_cfg, result)
            if volume:
                count += 1

        # Create snapshots
        for snapshot_cfg in config.snapshots:
            if self._create_snapshot(snapshot_cfg, result):
                count += 1

        result.resources_created["cinder"] = count

    def _create_volume(self, cfg: VolumeConfig, result: PresetResult) -> Any | None:
        """Create a volume."""
        if cfg.name in self._resource_map["volumes"]:
            logger.debug(f"Volume '{cfg.name}' already exists, skipping")
            return self.db.get_volume(self._resource_map["volumes"][cfg.name])

        project_id = self._resolve_project_id(cfg.project)
        user_id = self.db._default_user_id

        try:
            volume = self.db.create_volume(
                name=cfg.name,
                size=cfg.size,
                project_id=project_id,
                user_id=user_id,
                description=cfg.description,
                volume_type=cfg.volume_type,
            )
            self._resource_map["volumes"][cfg.name] = volume.id
            logger.info(f"Created volume: {cfg.name} ({volume.id})")

            # Attach to server if specified
            if cfg.attach_to:
                server_id = self._resolve_server_id(cfg.attach_to)
                if server_id:
                    self.db.attach_volume(
                        volume_id=volume.id,
                        server_id=server_id,
                        project_id=project_id,
                        device=cfg.device or "/dev/vdb",
                    )
                    logger.debug(f"Attached volume '{cfg.name}' to server '{cfg.attach_to}'")

            return volume
        except Exception as e:
            result.errors.append(f"Failed to create volume '{cfg.name}': {e}")
            return None

    def _create_snapshot(self, cfg: Any, result: PresetResult) -> Any | None:
        """Create a volume snapshot."""
        project_id = self._resolve_project_id(cfg.project)
        volume_id = self._resolve_volume_id(cfg.volume)

        if not volume_id:
            result.errors.append(f"Snapshot '{cfg.name}': volume '{cfg.volume}' not found")
            return None

        try:
            snapshot = self.db.create_snapshot(
                volume_id=volume_id,
                name=cfg.name,
                project_id=project_id,
                user_id=self.db._default_user_id,
                description=cfg.description,
            )
            if not snapshot:
                result.errors.append(
                    f"Failed to create snapshot '{cfg.name}': creation returned None"
                )
                return None
            logger.info(f"Created snapshot: {cfg.name} ({snapshot.id})")
            return snapshot
        except Exception as e:
            result.errors.append(f"Failed to create snapshot '{cfg.name}': {e}")
            return None

    def _apply_octavia(self, config: OctaviaConfig, result: PresetResult) -> None:
        """Apply Octavia resources."""
        count = 0

        for lb_cfg in config.load_balancers:
            lb, resource_count = self._create_load_balancer(lb_cfg, result)
            if lb:
                count += resource_count

        result.resources_created["octavia"] = count

    def _create_load_balancer(
        self, cfg: LoadBalancerConfig, result: PresetResult
    ) -> tuple[Any | None, int]:
        """Create a load balancer with listeners and pools."""
        if cfg.name in self._resource_map["load_balancers"]:
            logger.debug(f"Load balancer '{cfg.name}' already exists, skipping")
            lb_id = self._resource_map["load_balancers"][cfg.name]
            return self.db.get_load_balancer(lb_id), 0

        project_id = self._resolve_project_id(cfg.project)
        subnet_id = self._resolve_subnet_id(cfg.vip_subnet)

        if not subnet_id:
            result.errors.append(f"Load balancer '{cfg.name}': subnet '{cfg.vip_subnet}' not found")
            return None, 0

        try:
            lb = self.db.create_load_balancer(
                name=cfg.name,
                project_id=project_id,
                vip_subnet_id=subnet_id,
                vip_address=cfg.vip_address,
            )
            self._resource_map["load_balancers"][cfg.name] = lb.id
            logger.info(f"Created load balancer: {cfg.name} ({lb.id})")

            resource_count = 1

            # Create listeners
            for listener_cfg in cfg.listeners:
                listener, listener_count = self._create_listener(
                    listener_cfg, lb.id, project_id, result
                )
                if listener:
                    resource_count += listener_count

            return lb, resource_count
        except Exception as e:
            result.errors.append(f"Failed to create load balancer '{cfg.name}': {e}")
            return None, 0

    def _create_listener(
        self,
        cfg: ListenerConfig,
        lb_id: str,
        project_id: str,
        result: PresetResult,
    ) -> tuple[Any | None, int]:
        """Create a listener with optional pool."""
        try:
            listener = self.db.create_listener(
                name=cfg.name,
                loadbalancer_id=lb_id,
                protocol=cfg.protocol,
                protocol_port=cfg.port,
                project_id=project_id,
            )
            if not listener:
                return None, 0

            self._resource_map["listeners"][cfg.name] = listener.id
            logger.info(f"Created listener: {cfg.name} ({listener.id})")

            resource_count = 1

            # Create pool if specified
            if cfg.pool:
                pool, pool_count = self._create_pool(
                    cfg.pool, lb_id, listener.id, project_id, result
                )
                if pool:
                    resource_count += pool_count
                    # Update listener with pool
                    self.db.update_listener(
                        listener.id, project_id=project_id, default_pool_id=pool.id
                    )

            return listener, resource_count
        except Exception as e:
            result.errors.append(f"Failed to create listener '{cfg.name}': {e}")
            return None, 0

    def _create_pool(
        self,
        cfg: PoolConfig,
        lb_id: str,
        listener_id: str,
        project_id: str,
        result: PresetResult,
    ) -> tuple[Any | None, int]:
        """Create a pool with members."""
        try:
            pool = self.db.create_pool(
                name=cfg.name,
                protocol=cfg.protocol,
                lb_algorithm=cfg.lb_algorithm,
                project_id=project_id,
                loadbalancer_id=lb_id,
                listener_id=listener_id,
            )
            if not pool:
                return None, 0

            self._resource_map["pools"][cfg.name] = pool.id
            logger.info(f"Created pool: {cfg.name} ({pool.id})")

            resource_count = 1

            # Create members
            for member_cfg in cfg.members:
                address = member_cfg.address
                if not address and member_cfg.server:
                    # Get server IP
                    server_id = self._resolve_server_id(member_cfg.server)
                    if server_id:
                        server = self.db.get_server(server_id)
                        if server and server.addresses:
                            for addrs in server.addresses.values():
                                if addrs:
                                    address = addrs[0].get("addr")
                                    break

                if address:
                    member = self.db.create_pool_member(
                        pool_id=pool.id,
                        address=address,
                        protocol_port=member_cfg.port,
                        project_id=project_id,
                        weight=member_cfg.weight,
                    )
                    if member:
                        resource_count += 1
                        logger.debug(f"Created pool member: {address}:{member_cfg.port}")

            return pool, resource_count
        except Exception as e:
            result.errors.append(f"Failed to create pool '{cfg.name}': {e}")
            return None, 0
