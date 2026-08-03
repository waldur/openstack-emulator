"""In-memory database for OpenStack emulator."""

import ipaddress
import json
import logging
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_DNS, uuid4, uuid5

from emulator.core import persistence
from emulator.core.exceptions import (
    FixedIPAlreadyInUseError,
    InvalidFixedIPError,
    IpAddressGenerationFailureError,
    PortInUseError,
    PortNotFoundError,
    ScopeUnauthorizedError,
)
from emulator.core.models import (
    AllocationPool,
    ApplicationCredential,
    BackupStatus,
    CinderQuota,
    ConsistencyGroup,
    ContainerFormat,
    Credential,
    DiskFormat,
    Domain,
    Endpoint,
    ExternalGatewayInfo,
    FederationMapping,
    FederationProtocol,
    FixedIP,
    Flavor,
    FloatingIP,
    FloatingIPStatus,
    GlanceImage,
    GlanceStore,
    Group,
    GroupSnapshot,
    GroupStatus,
    HealthMonitor,
    HealthMonitorType,
    IdentityProvider,
    Image,
    ImageCacheEntry,
    ImageMember,
    ImageStatus,
    ImageTask,
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
    LoadBalancerAvailabilityZone,
    LoadBalancerAvailabilityZoneProfile,
    LoadBalancerFlavor,
    LoadBalancerFlavorProfile,
    LoadBalancerOperatingStatus,
    LoadBalancerProvider,
    LoadBalancerProvisioningStatus,
    MetadefNamespace,
    Network,
    NetworkStatus,
    NeutronAgent,
    NeutronExtension,
    NeutronFlavor,
    NeutronQuota,
    NovaExtension,
    NovaQuota,
    OctaviaQuota,
    OidcAuthorizationCode,
    OidcClient,
    OidcUser,
    PolicyDocument,
    Pool,
    PoolLBAlgorithm,
    PoolMember,
    PoolProtocol,
    Port,
    PortStatus,
    PowerState,
    Project,
    QosPolicy,
    QosRuleType,
    QosSpec,
    RbacPolicy,
    Region,
    RegisteredLimit,
    RemoteConsole,
    ResourceProvider,
    Role,
    RoleAssignment,
    Router,
    RouterStatus,
    SecurityGroup,
    SecurityGroupRule,
    Server,
    ServerConsole,
    ServerDiagnostics,
    ServerGroup,
    ServerNetworkInterface,
    ServerStatus,
    ServerVolumeAttachment,
    Service,
    ServiceProfile,
    ServiceProvider,
    Snapshot,
    SnapshotStatus,
    Subnet,
    SwiftAccount,
    SwiftContainer,
    SwiftObject,
    TaskStatus,
    TaskType,
    Token,
    Trunk,
    TrunkSubPort,
    User,
    Volume,
    VolumeAttachment,
    VolumeBackup,
    VolumeStatus,
    VolumeTransfer,
    VolumeType,
)

logger = logging.getLogger(__name__)

# Neutron device owner constants
DEVICE_OWNER_FLOATINGIP = "network:floatingip"
DEVICE_OWNER_ROUTER_INTERFACE = "network:router_interface"
DEVICE_OWNER_ROUTER_GATEWAY = "network:router_gateway"


def default_resource_id(name: str) -> str:
    """Return the stable id of a seeded default resource.

    The seeded Neutron defaults used to get a fresh uuid4() on every boot, which
    made them impossible to reference from anything static. A client configured
    with a network id — Waldur's external_network_id setting, say — cannot carry
    that value in a fixture or preset if it changes each time the emulator
    starts, forcing every caller to discover it at runtime first.

    Deriving from a fixed namespace keeps the ids valid UUIDs (callers do
    validate) while making them reproducible across boots and across machines.
    """
    return str(uuid5(NAMESPACE_DNS, f"openstack-emulator:default:{name}"))


class Database:
    """In-memory database for storing OpenStack resources."""

    def __init__(self, persist_path: str | None = None, auto_save: bool = False) -> None:
        """Initialize the database with optional persistence."""
        self._lock = threading.RLock()
        self.persist_path = persist_path
        self.auto_save = auto_save
        # Shift applied to every port in the service catalog, so a catalog built
        # under --port-offset names the ports the services are actually bound to.
        # A deployment parameter rather than state: set at startup, never saved.
        self.port_offset = 0
        # Set when a load could not read everything, so the first save keeps a
        # copy of the original instead of silently replacing it.
        self._load_degraded = False
        self._backup_done = False

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

        # Storage dictionaries - Nova Server Groups
        self._server_groups: dict[str, ServerGroup] = {}

        # Storage dictionaries - Quotas
        self._nova_quotas: dict[str, NovaQuota] = {}
        self._neutron_quotas: dict[str, NeutronQuota] = {}
        self._cinder_quotas: dict[str, CinderQuota] = {}
        # Quota classes hold the limits new projects inherit, keyed by class name
        # ("default" is the only one most deployments ever use).
        self._cinder_quota_classes: dict[str, CinderQuota] = {}
        self._nova_quota_classes: dict[str, NovaQuota] = {}

        self._service_providers: dict[str, ServiceProvider] = {}

        # Storage dictionaries - embedded OpenID Provider
        self._oidc_clients: dict[str, OidcClient] = {}
        self._oidc_users: dict[str, OidcUser] = {}
        self._oidc_codes: dict[str, OidcAuthorizationCode] = {}

        # Storage dictionaries - Swift object storage. Containers and objects
        # are keyed by their full path so a name is only unique within its
        # parent, as in Swift.
        self._swift_accounts: dict[str, SwiftAccount] = {}
        self._swift_containers: dict[str, SwiftContainer] = {}
        self._swift_objects: dict[str, SwiftObject] = {}

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

        # Storage dictionaries - Nova Extensions
        self._server_volume_attachments: dict[
            str, list[ServerVolumeAttachment]
        ] = {}  # server_id -> attachments
        self._server_network_interfaces: dict[
            str, list[ServerNetworkInterface]
        ] = {}  # server_id -> interfaces
        self._server_consoles: dict[str, list[ServerConsole]] = {}  # server_id -> consoles
        self._server_tags: dict[str, set[str]] = {}  # server_id -> tags
        self._nova_extensions: dict[str, NovaExtension] = {}

        # Storage dictionaries - Neutron Extensions
        self._qos_policies: dict[str, QosPolicy] = {}
        self._qos_rule_types: dict[str, QosRuleType] = {}
        self._neutron_agents: dict[str, NeutronAgent] = {}
        self._trunks: dict[str, Trunk] = {}
        self._neutron_extensions: dict[str, NeutronExtension] = {}
        self._neutron_flavors: dict[str, NeutronFlavor] = {}
        self._service_profiles: dict[str, ServiceProfile] = {}

        # Storage dictionaries - Octavia Extensions
        self._octavia_quotas: dict[str, OctaviaQuota] = {}
        self._lb_flavors: dict[str, LoadBalancerFlavor] = {}
        self._lb_flavor_profiles: dict[str, LoadBalancerFlavorProfile] = {}
        self._lb_availability_zones: dict[str, LoadBalancerAvailabilityZone] = {}
        self._lb_availability_zone_profiles: dict[str, LoadBalancerAvailabilityZoneProfile] = {}
        self._lb_providers: dict[str, LoadBalancerProvider] = {}

        # Storage dictionaries - Cinder Extensions
        self._volume_transfers: dict[str, VolumeTransfer] = {}
        self._volume_backups: dict[str, VolumeBackup] = {}
        self._consistency_groups: dict[str, ConsistencyGroup] = {}
        self._group_snapshots: dict[str, GroupSnapshot] = {}

        # Storage dictionaries - Glance Extensions
        self._image_tasks: dict[str, ImageTask] = {}
        self._metadef_namespaces: dict[str, MetadefNamespace] = {}
        self._image_cache: dict[str, ImageCacheEntry] = {}
        self._glance_stores: dict[str, GlanceStore] = {}

        # Storage dictionaries - Keystone Extensions
        self._application_credentials: dict[str, ApplicationCredential] = {}  # key: user_id:cred_id
        self._policy_documents: dict[str, PolicyDocument] = {}
        self._identity_providers: dict[str, IdentityProvider] = {}
        self._federation_protocols: dict[str, FederationProtocol] = {}  # key: idp_id:protocol_id
        self._federation_mappings: dict[str, FederationMapping] = {}
        self._registered_limits: dict[str, RegisteredLimit] = {}

        # Storage dictionaries - Placement
        self._resource_providers: dict[str, ResourceProvider] = {}

        # Initialize with default data
        self._init_default_flavors()
        self._init_default_images()
        self._init_default_glance_images()
        self._init_default_keystone_data()
        self._init_default_volume_types()
        self._init_default_neutron_data()
        self._init_default_tokens()
        self._init_nova_extensions()
        self._init_neutron_extensions()
        self._init_octavia_extensions()
        self._init_glance_extensions()
        self._init_keystone_extensions()
        self._init_default_resource_providers()

        # Load persisted data if enabled
        if self.persist_path:
            self.load()

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
        import hashlib

        self._default_user_id = str(uuid4())
        self._default_user_name = "admin"
        admin_password_hash = hashlib.sha256("s4l4dus".encode()).hexdigest()
        admin_user = User(
            id=self._default_user_id,
            name=self._default_user_name,
            description="Admin user",
            domain_id="default",
            default_project_id=self._default_project_id,
            enabled=True,
            email="admin@example.com",
            password_hash=admin_password_hash,
        )
        self._users[admin_user.id] = admin_user

        # Create default roles (including standard OpenStack role name variations)
        admin_role = Role(id=str(uuid4()), name="admin", description="Admin role")
        member_role = Role(id=str(uuid4()), name="member", description="Member role")
        member_cap_role = Role(
            id=str(uuid4()), name="Member", description="Member role (capitalized)"
        )
        member_underscore_role = Role(
            id=str(uuid4()), name="_member_", description="Member role (legacy)"
        )
        reader_role = Role(id=str(uuid4()), name="reader", description="Reader role")
        manager_role = Role(id=str(uuid4()), name="manager", description="Manager role")

        self._roles[admin_role.id] = admin_role
        self._roles[member_role.id] = member_role
        self._roles[member_cap_role.id] = member_cap_role
        self._roles[member_underscore_role.id] = member_underscore_role
        self._roles[reader_role.id] = reader_role
        self._roles[manager_role.id] = manager_role

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

        # Object Storage service (Swift)
        object_store_service = Service(
            id=str(uuid4()),
            name="swift",
            type="object-store",
            description="OpenStack Object Storage Service",
            enabled=True,
        )
        self._services[object_store_service.id] = object_store_service

        # Rating service (CloudKitty)
        rating_service = Service(
            id=str(uuid4()),
            name="cloudkitty",
            type="rating",
            description="OpenStack Rating Service",
            enabled=True,
        )
        self._services[rating_service.id] = rating_service

        # Store service IDs for catalog generation
        self._service_ids = {
            "identity": identity_service.id,
            "compute": compute_service.id,
            "image": image_service.id,
            "volumev3": volume_service.id,
            "object-store": object_store_service.id,
            "rating": rating_service.id,
        }

    def _init_default_volume_types(self) -> None:
        """Create default volume types matching real OpenStack patterns."""
        default_types = [
            VolumeType(
                id=str(uuid4()),
                name="__DEFAULT__",
                description="Default volume type",
                is_public=False,
                extra_specs={},
            ),
            VolumeType(
                id=str(uuid4()),
                name="lvmdriver-1",
                description="Default LVM volume type",
                is_public=True,
                extra_specs={},
            ),
            VolumeType(
                id=str(uuid4()),
                name="prod",
                description="Shared production HDD",
                is_public=False,
                extra_specs={"volume_backend_name": "prod"},
            ),
            VolumeType(
                id=str(uuid4()),
                name="rbd",
                description="Ceph RBD storage",
                is_public=False,
                extra_specs={"volume_backend_name": "rbd"},
            ),
            VolumeType(
                id=str(uuid4()),
                name="ssd",
                description="IOPS intensive SSD",
                is_public=True,
                extra_specs={"volume_backend_name": "ssd"},
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
        project_domain_id: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
        methods: list[str] | None = None,
        unscoped: bool = False,
        is_federated: bool = False,
        idp_id: str = "",
        protocol_id: str = "",
        groups: list[str] | None = None,
        roles: list[dict[str, str]] | None = None,
    ) -> Token:
        """Create a new authentication token.

        Args:
            user_name: Name of the authenticating user.
            project_name: Name of the project to scope to.
            base_url: Request base URL, used to build the service catalog.
            domain_id: Domain the user belongs to.
            project_domain_id: Domain the scoped project belongs to. Keystone
                treats it as independent of the user's domain; defaults to it.
            project_id: Project id to scope to; takes precedence over the name.
            user_id: User id to scope to; takes precedence over the name.
            methods: Authentication methods recorded on the token.
            unscoped: Issue a token with no project and no catalog.
            is_federated: Mark the token as produced by OS-FEDERATION.
            idp_id: Identity provider that authenticated the user.
            protocol_id: Federation protocol used.
            groups: Federated group ids mapped for this user.
            roles: Authoritative role list, overriding what the user holds on the
                project. Used by application credentials, whose role list is a
                deliberately narrowed subset.
        """
        with self._lock:
            # Find user by id when given (federated rescoping knows the exact
            # user), otherwise by name and domain.
            user = self._users.get(user_id) if user_id else None
            if not user:
                user = self.get_user_by_name(user_name, domain_id)
            if not user:
                # A name nobody registered still authenticates — the emulator
                # cannot check passwords — but it must not become somebody else.
                # This used to hand back _default_user_id, which is the seeded
                # admin's id, so any unrecognised name inherited the admin's
                # role assignments and could scope anywhere they could. The
                # identity is now derived from the name, so it is stable across
                # calls and holds no assignments until something grants one.
                user = User(
                    id=str(uuid5(NAMESPACE_DNS, f"{domain_id}:{user_name}")),
                    name=user_name,
                    domain_id=domain_id,
                )

            # Resolve the project. Clients (e.g. Waldur) scope tenant sessions by
            # project id, so when an id is given resolve by it (and never fall
            # back to a name lookup, which would wrongly attribute the token to
            # the admin project); otherwise resolve by name.
            project = None
            if unscoped:
                project = None
            elif project_id:
                project = self.get_project(project_id)
            else:
                project = self.get_project_by_name(project_name, project_domain_id or domain_id)
            if not project and not unscoped:
                # Synthesize a project, preserving the requested id if any so the
                # token stays consistent with the scope the client asked for.
                # An unnamed scope gets a name derived from the id rather than
                # an empty one: "admin" is a privileged name, so a synthesized
                # project must never accidentally acquire it.
                project = Project(
                    id=project_id or self._default_project_id,
                    name=project_name or f"project-{project_id}",
                    domain_id=project_domain_id or domain_id,
                )

            # Roles the user genuinely holds on this project. Keep these apart
            # from the fallback below: only real assignments confer privilege.
            explicit_roles = self.get_user_roles_on_project(user.id, project.id) if project else []
            if roles is not None:
                explicit_roles = list(roles)
            token_roles = list(explicit_roles)
            if not token_roles and not unscoped:
                # Keystone will not mint a scoped token that would carry no
                # roles: TokenModel.mint calls _validate_project_scope, which
                # raises Unauthorized. Reproduced so that a client scoping to a
                # project it was never granted fails here the way it would fail
                # against a real cloud, instead of quietly receiving a usable
                # token.
                raise ScopeUnauthorizedError(user.id, project.id if project else "")

            is_admin = (project.name or "").lower() == "admin" if project else False
            if any(role["name"].lower() == "admin" for role in explicit_roles):
                is_admin = True

            # Get domain info
            domain = self._domains.get(domain_id, self._default_domain)

            token = Token(
                id=str(uuid4()),
                user_id=user.id,
                user_name=user.name,
                project_id=project.id if project else "",
                project_name=project.name if project else "",
                domain_id=domain.id,
                domain_name=domain.name,
                roles=token_roles,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                catalog=(
                    [] if project is None else self._generate_service_catalog(base_url, project.id)
                ),
                methods=methods or ["password"],
                is_admin=is_admin,
                unscoped=unscoped,
                is_federated=is_federated,
                idp_id=idp_id,
                protocol_id=protocol_id,
                groups=list(groups or []),
            )
            logger.info("Storing token in database: %s for user %s", token.id, user.name)
            self._tokens[token.id] = token
            logger.debug(
                "Database now has %d tokens: %s", len(self._tokens), list(self._tokens.keys())
            )
            logger.debug("Token %s expires at: %s", token.id, token.expires_at)
            return token

    def validate_token(self, token_id: str) -> Token | None:
        """Validate and return a token if valid."""
        logger.debug("Validating token: %s", token_id)
        with self._lock:
            logger.debug(
                "Database currently has %d tokens: %s", len(self._tokens), list(self._tokens.keys())
            )
            token = self._tokens.get(token_id)
            logger.debug("Token found in db: %s", token is not None)
            if token:
                logger.debug(
                    "Token expires_at: %s, current time: %s",
                    token.expires_at,
                    datetime.now(timezone.utc),
                )
                if token.expires_at and token.expires_at > datetime.now(timezone.utc):
                    logger.debug("Token is valid")
                    return token
                else:
                    logger.debug("Token is expired")
            else:
                logger.debug("Token not found in database")
            return None

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token."""
        with self._lock:
            if token_id in self._tokens:
                del self._tokens[token_id]
                return True
            return False

    def _generate_service_catalog(
        self, base_url: str, project_id: str = ""
    ) -> list[dict[str, Any]]:
        """Generate a service catalog for tokens.

        Uses standard OpenStack ports, shifted by :attr:`port_offset`:
        - Keystone (Identity): 5000
        - Nova (Compute): 8774
        - Cinder (Block Storage): 8776
        - Glance (Image): 9292
        - Neutron (Network): 9696
        - Octavia (Load Balancer): 9876

        The offset matters because clients reach every service through this
        catalog. Advertising 8774 while Nova listens on 8874 leaves an SDK
        client dialling a closed port, so ``--port-offset`` has to reach here
        as well as the listeners.
        """
        from urllib.parse import urlparse

        # Parse the base URL to extract host for building service URLs
        parsed = urlparse(base_url)
        host = parsed.hostname or "localhost"
        scheme = parsed.scheme or "http"

        def url_for(port: int) -> str:
            return f"{scheme}://{host}:{port + self.port_offset}"

        keystone_url = url_for(5000)
        nova_url = url_for(8774)
        cinder_url = url_for(8776)
        glance_url = url_for(9292)
        neutron_url = url_for(9696)
        octavia_url = url_for(9876)
        placement_url = url_for(8778)
        swift_url = url_for(8080)
        rating_url = url_for(8889)

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
                        "url": f"{cinder_url}/v3/{project_id}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{cinder_url}/v3/{project_id}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{cinder_url}/v3/{project_id}",
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
            {
                "type": "load-balancer",
                "name": "octavia",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{octavia_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{octavia_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{octavia_url}",
                    },
                ],
            },
            {
                "type": "placement",
                "name": "placement",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{placement_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{placement_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{placement_url}",
                    },
                ],
            },
            {
                "type": "rating",
                "name": "cloudkitty",
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{rating_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{rating_url}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{rating_url}",
                    },
                ],
            },
            {
                "type": "object-store",
                "name": "swift",
                # The account segment is part of the endpoint, so a client that
                # follows the catalog addresses its own AUTH_<project> account
                # and nothing else — the same reason a Swift quota can only be
                # set on the account the storage URL points at.
                "endpoints": [
                    {
                        "region": "RegionOne",
                        "interface": "public",
                        "url": f"{swift_url}/v1/AUTH_{project_id}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "internal",
                        "url": f"{swift_url}/v1/AUTH_{project_id}",
                    },
                    {
                        "region": "RegionOne",
                        "interface": "admin",
                        "url": f"{swift_url}/v1/AUTH_{project_id}",
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
        config_drive: bool | None = None,
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
                # Nova returns this field as the string "True" or "" (empty
                # for False). Match that wire format here.
                config_drive="True" if config_drive else "",
                admin_pass=str(uuid4())[:12],
                progress=0,
            )

            # Bind the requested networks/ports for real. Nova allocates a port
            # per network request and stamps it with the instance, so anything
            # that follows a server's ports by device_id depends on this having
            # happened; synthesising addresses alone left every such lookup
            # empty. Done before the server is registered so a bad request
            # leaves nothing behind.
            if networks:
                interfaces = self._bind_server_networks(server_id, server, networks)
                server.addresses = self._addresses_from_interfaces(interfaces)
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

            if self.auto_save:
                self.save()

            return server

    def _complete_server_build(self, server_id: str) -> None:
        """Simulate server build completion."""
        server = self._servers.get(server_id)
        if server:
            server.status = ServerStatus.ACTIVE
            server.power_state = PowerState.RUNNING
            server.progress = 100
            server.launched_at = datetime.now(timezone.utc)
            server.updated = datetime.now(timezone.utc)

    def _bind_server_networks(
        self, server_id: str, server: Server, networks: list[dict[str, Any]]
    ) -> list[ServerNetworkInterface]:
        """Allocate and bind a port for each network request on a server.

        Mirrors Nova's allocate_for_instance: a request naming a ``port`` binds
        that existing port, and a request naming a network ``uuid`` has Nova
        create the port first (and own it, so it is deleted rather than unbound
        when the interface goes away). Either way the port ends up carrying
        ``device_id`` and ``device_owner``, which is what makes
        ``list_ports(device_id=<server>)`` and ``os-interface`` agree with
        reality.

        Raises:
            PortNotFoundError: A requested port or network does not exist.
            PortInUseError: A requested port is already bound to a device.
        """
        interfaces: list[ServerNetworkInterface] = []
        for request in networks:
            port_id = request.get("port")
            network_id = request.get("uuid")

            if port_id:
                port = self._ports.get(port_id)
                if port is None:
                    raise PortNotFoundError(port_id)
                nova_created = False
            elif network_id:
                if network_id not in self._networks:
                    raise PortNotFoundError(network_id)
                fixed_ips = (
                    [{"ip_address": request["fixed_ip"]}] if request.get("fixed_ip") else None
                )
                port = self.create_port(
                    network_id=network_id,
                    project_id=server.tenant_id,
                    fixed_ips=fixed_ips,
                    validate_fixed_ips=bool(fixed_ips),
                )
                if port is None:
                    raise PortNotFoundError(network_id)
                nova_created = True
            else:
                continue

            interfaces.append(
                self.attach_interface_to_server(
                    server_id,
                    port,
                    nova_created=nova_created,
                    availability_zone=server.availability_zone,
                )
            )
        return interfaces

    def _addresses_from_interfaces(
        self, interfaces: list[ServerNetworkInterface]
    ) -> dict[str, list[dict[str, Any]]]:
        """Build the server ``addresses`` map from its bound ports.

        Keyed by network name, as Nova does, rather than by network id.
        """
        addresses: dict[str, list[dict[str, Any]]] = {}
        for interface in interfaces:
            network = self._networks.get(interface.net_id)
            key = network.name if network else interface.net_id
            entries = addresses.setdefault(key, [])
            for fixed_ip in interface.fixed_ips:
                entries.append(
                    {
                        "addr": fixed_ip.get("ip_address", ""),
                        "version": 4,
                        "OS-EXT-IPS:type": "fixed",
                        "OS-EXT-IPS-MAC:mac_addr": interface.mac_addr,
                    }
                )
        return addresses

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
                server.updated = datetime.now(timezone.utc)
                if self.auto_save:
                    self.save()
            return server

    def delete_server(self, server_id: str) -> bool:
        """Delete a server.

        Attached interfaces are released like Nova's deallocate_for_instance:
        Nova-created ports are deleted, pre-existing ports are unbound.

        Attached volumes are detached the way Nova's _cleanup_volumes does. A
        volume left carrying an attachment to a server that no longer exists
        reads as in-use forever and can never be deleted or re-attached.
        """
        with self._lock:
            if server_id in self._servers:
                server = self._servers[server_id]
                server.status = ServerStatus.DELETED
                server.terminated_at = datetime.now(timezone.utc)
                server.updated = datetime.now(timezone.utc)
                del self._servers[server_id]
                for interface in self._server_network_interfaces.pop(server_id, []):
                    self._release_interface_port(interface, server_id)
                self._detach_server_volumes(server_id)
                if self.auto_save:
                    self.save()
                return True
            return False

    # Server actions
    def _detach_server_volumes(self, server_id: str) -> None:
        """Release every volume attached to a server that is going away.

        Caller holds the lock. A volume marked ``delete_on_termination`` goes
        with the instance, as in Nova; the rest return to ``available``.
        """
        for attachment in self._server_volume_attachments.pop(server_id, []):
            volume = self._volumes.get(attachment.volume_id)
            if volume is None:
                continue
            volume.attachments = [a for a in volume.attachments if a.server_id != server_id]
            if attachment.delete_on_termination:
                self._volumes.pop(attachment.volume_id, None)
                continue
            if not volume.attachments:
                volume.status = VolumeStatus.AVAILABLE
            volume.updated_at = datetime.now(timezone.utc)

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
                    server.updated = datetime.now(timezone.utc)
                    if self.auto_save:
                        self.save()
                    return True

            elif action_lower == "stop" or action_lower == "os-stop":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SHUTOFF
                    server.power_state = PowerState.SHUTDOWN
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "reboot":
                if server.status in [ServerStatus.ACTIVE, ServerStatus.SHUTOFF]:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "pause":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.PAUSED
                    server.power_state = PowerState.PAUSED
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "unpause":
                if server.status == ServerStatus.PAUSED:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "suspend":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SUSPENDED
                    server.power_state = PowerState.SUSPENDED
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "resume":
                if server.status == ServerStatus.SUSPENDED:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "shelve":
                if server.status == ServerStatus.ACTIVE:
                    server.status = ServerStatus.SHELVED
                    server.power_state = PowerState.SHUTDOWN
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "unshelve":
                if server.status in [ServerStatus.SHELVED, ServerStatus.SHELVED_OFFLOADED]:
                    server.status = ServerStatus.ACTIVE
                    server.power_state = PowerState.RUNNING
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "confirmresize":
                if server.status == ServerStatus.VERIFY_RESIZE:
                    # Restore to pre-resize status (ACTIVE or SHUTOFF)
                    if server.pre_resize_status == ServerStatus.SHUTOFF:
                        server.status = ServerStatus.SHUTOFF
                        server.power_state = PowerState.SHUTDOWN
                    else:
                        server.status = ServerStatus.ACTIVE
                        server.power_state = PowerState.RUNNING
                    # Clear resize tracking fields
                    server.original_flavor_id = None
                    server.pre_resize_status = None
                    server.updated = datetime.now(timezone.utc)
                    return True

            elif action_lower == "revertresize":
                if server.status == ServerStatus.VERIFY_RESIZE:
                    # Revert to original flavor
                    if server.original_flavor_id:
                        server.flavor_id = server.original_flavor_id
                    # Restore to pre-resize status (ACTIVE or SHUTOFF)
                    if server.pre_resize_status == ServerStatus.SHUTOFF:
                        server.status = ServerStatus.SHUTOFF
                        server.power_state = PowerState.SHUTDOWN
                    else:
                        server.status = ServerStatus.ACTIVE
                        server.power_state = PowerState.RUNNING
                    # Clear resize tracking fields
                    server.original_flavor_id = None
                    server.pre_resize_status = None
                    server.updated = datetime.now(timezone.utc)
                    return True

            return False

    def server_resize(self, server_id: str, flavor_id: str) -> bool:
        """Resize a server to a new flavor.

        Transitions: ACTIVE/SHUTOFF -> RESIZE -> VERIFY_RESIZE
        In the emulator, we skip RESIZE and go directly to VERIFY_RESIZE.
        """
        with self._lock:
            server = self._servers.get(server_id)
            if not server:
                return False

            # Can only resize from ACTIVE or SHUTOFF
            if server.status not in [ServerStatus.ACTIVE, ServerStatus.SHUTOFF]:
                return False

            # Validate the new flavor exists
            if flavor_id not in self._flavors:
                return False

            # Store original flavor and status for potential revert
            server.original_flavor_id = server.flavor_id
            server.pre_resize_status = server.status

            # Update to new flavor
            server.flavor_id = flavor_id

            # Transition to VERIFY_RESIZE (skipping RESIZE state for simplicity)
            server.status = ServerStatus.VERIFY_RESIZE
            server.power_state = PowerState.SHUTDOWN
            server.updated = datetime.now(timezone.utc)
            return True

    def create_server_snapshot(
        self,
        server_id: str,
        name: str,
        metadata: dict[str, str] | None = None,
    ) -> GlanceImage | None:
        """Create a snapshot image from a server.

        Returns the created GlanceImage or None if server not found.
        """
        with self._lock:
            server = self._servers.get(server_id)
            if not server:
                return None

            # Create a new Glance image as a snapshot
            image = GlanceImage(
                id=str(uuid4()),
                name=name,
                status=ImageStatus.ACTIVE,  # Immediately active in emulator
                visibility=ImageVisibility.PRIVATE,
                protected=False,
                owner=server.tenant_id,
                min_disk=0,
                min_ram=0,
                container_format=ContainerFormat.BARE,
                disk_format=DiskFormat.QCOW2,
                size=1073741824,  # Fake 1GB size
                properties={
                    "image_type": "snapshot",
                    "instance_uuid": server_id,
                    "base_image_ref": server.image_id,
                    **(metadata or {}),
                },
            )
            self._glance_images[image.id] = image
            self._images[image.id] = image.to_nova_image()
            self._image_members[image.id] = []
            return image

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
            if self.auto_save:
                self.save()
            return flavor

    def delete_flavor(self, flavor_id: str) -> bool:
        """Delete a flavor."""
        with self._lock:
            if flavor_id in self._flavors:
                del self._flavors[flavor_id]
                if self.auto_save:
                    self.save()
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
            if self.auto_save:
                self.save()
            return image

    def delete_image(self, image_id: str) -> bool:
        """Delete an image."""
        with self._lock:
            if image_id in self._images:
                del self._images[image_id]
                if self.auto_save:
                    self.save()
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
            if self.auto_save:
                self.save()
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
                if self.auto_save:
                    self.save()
                return True
            return False

    # Persistence
    def save(self) -> None:
        """Write the whole database to disk.

        The write is atomic (temp file + rename) so an interrupted save cannot
        leave a truncated file behind. If the last load dropped records, the
        original file is copied aside first: overwriting a file we could not
        fully read would turn a recoverable problem into permanent data loss.
        """
        if not self.persist_path:
            return

        with self._lock:
            try:
                lossy = False
                data: dict[str, Any] = {"schema_version": persistence.SCHEMA_VERSION}
                for collection in persistence.PERSISTED:
                    try:
                        encoded, dropped = persistence.encode_collection(
                            collection, getattr(self, collection.attr)
                        )
                    except Exception as e:
                        # The container itself is unusable. Omitting the key
                        # leaves the in-memory defaults in place on the next
                        # load, which beats abandoning the whole write.
                        logger.error(f"Could not serialize '{collection.key}', omitting it: {e}")
                        lossy = True
                        continue
                    data[collection.key] = encoded
                    for failure in dropped:
                        logger.error(
                            f"Dropped unserializable record from '{collection.key}' -> {failure}"
                        )
                    lossy = lossy or bool(dropped)

                data["scalars"] = {
                    name: getattr(self, name) for name in persistence.PERSISTED_SCALARS
                }

                path = Path(self.persist_path)
                path.parent.mkdir(parents=True, exist_ok=True)

                # Keep the last file we cannot faithfully reproduce, whether the
                # gap came from reading it or from writing this one.
                if self._load_degraded or lossy:
                    self._backup_existing_file(path)

                tmp = path.with_name(f"{path.name}.tmp")
                try:
                    with open(tmp, "w") as f:
                        json.dump(data, f, indent=2)
                    os.replace(tmp, path)
                except Exception:
                    # Never leave a half-written temp file next to the database.
                    tmp.unlink(missing_ok=True)
                    raise
                logger.info(f"Database saved to {self.persist_path}")
            except Exception as e:
                logger.error(f"Failed to save database: {e}")

    def _backup_existing_file(self, path: Path) -> None:
        """Preserve the current file once, before replacing it with a lossy one."""
        if self._backup_done or not path.exists():
            return
        self._backup_done = True
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            shutil.copy2(path, backup)
            logger.error(
                f"Database at {path} could not be read or written faithfully; original "
                f"preserved at {backup} before overwriting"
            )
        except Exception as e:  # pragma: no cover - best effort
            logger.error(f"Could not back up {path}: {e}")

    def load(self) -> None:
        """Restore database state from disk.

        Each collection, and each record within it, is decoded independently.
        A malformed record is logged and skipped rather than discarding
        everything after it, which is what the previous single try/except did.
        """
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if not path.exists():
            logger.info(f"No persistence file found at {self.persist_path}, starting fresh")
            return

        with self._lock:
            try:
                with open(path) as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read database at {self.persist_path}: {e}")
                self._load_degraded = True
                return

            if data.get("schema_version") is None:
                self._load_legacy_v1(data)
            else:
                self._load_current(data)

            # Nova's image view is a projection of the Glance images.
            for glance_img in self._glance_images.values():
                self._images[glance_img.id] = glance_img.to_nova_image()

            logger.info(f"Database loaded from {self.persist_path}")

    def _load_current(self, data: dict[str, Any]) -> None:
        """Load a schema_version >= 2 file."""
        dropped_total = 0
        for collection in persistence.PERSISTED:
            if collection.key not in data:
                continue
            try:
                value, dropped = persistence.decode_collection(collection, data[collection.key])
            except Exception as e:
                logger.error(f"Could not load '{collection.key}', keeping defaults: {e}")
                self._load_degraded = True
                continue
            setattr(self, collection.attr, value)
            for failure in dropped:
                logger.error(f"Dropped unreadable record from '{collection.key}' -> {failure}")
            dropped_total += len(dropped)

        for name, value in data.get("scalars", {}).items():
            if name in persistence.PERSISTED_SCALARS:
                setattr(self, name, value)

        if dropped_total:
            self._load_degraded = True

    def _load_legacy_v1(self, data: dict[str, Any]) -> None:
        """Load a file written before the format was versioned.

        Only the 17 collections the old ``save()`` knew about are present. The
        next save rewrites the file in the current format, so this path runs at
        most once per deployment after an upgrade.
        """
        logger.info("Persistence file predates schema versioning; upgrading on next save")
        legacy: list[tuple[str, str, Any]] = [
            ("servers", "_servers", self._dict_to_server),
            ("flavors", "_flavors", self._dict_to_flavor),
            ("images", "_images", self._dict_to_image),
            ("keypairs", "_keypairs", self._dict_to_keypair),
            ("domains", "_domains", self._dict_to_domain),
            ("projects", "_projects", self._dict_to_project),
            ("users", "_users", self._dict_to_user),
            ("roles", "_roles", self._dict_to_role),
            ("networks", "_networks", self._dict_to_network),
            ("subnets", "_subnets", self._dict_to_subnet),
            ("ports", "_ports", self._dict_to_port),
            ("routers", "_routers", self._dict_to_router),
            ("floating_ips", "_floating_ips", self._dict_to_floating_ip),
            ("security_groups", "_security_groups", self._dict_to_security_group),
            ("volumes", "_volumes", self._dict_to_volume),
            ("snapshots", "_snapshots", self._dict_to_snapshot),
            ("volume_types", "_volume_types", self._dict_to_volume_type),
            ("glance_images", "_glance_images", self._dict_to_glance_image),
        ]

        for key, attr, builder in legacy:
            if key not in data:
                continue
            loaded = {}
            for record_id, record in data[key].items():
                try:
                    loaded[record_id] = builder(record)
                except Exception as e:
                    self._load_degraded = True
                    logger.error(f"Dropped unreadable record {record_id} from '{key}': {e}")
            setattr(self, attr, loaded)

        if "role_assignments" in data:
            assignments = []
            for record in data["role_assignments"]:
                try:
                    assignments.append(self._dict_to_role_assignment(record))
                except Exception as e:
                    self._load_degraded = True
                    logger.error(f"Dropped unreadable role assignment: {e}")
            self._role_assignments = assignments

    # Legacy deserialization methods, used only by _load_legacy_v1.
    #
    # Do not extend these: state written today goes through
    # emulator.core.persistence, which derives the mapping from the dataclass
    # annotations. These exist purely to read files written before that.

    def _dict_to_server(self, data: dict[str, Any]) -> Server:
        """Convert dictionary to Server object."""
        return Server(
            id=data["id"],
            name=data["name"],
            status=ServerStatus(data["status"]),
            power_state=PowerState(data["power_state"]),
            tenant_id=data["tenant_id"],
            user_id=data["user_id"],
            flavor_id=data["flavor_id"],
            image_id=data["image_id"],
            host=data["host"],
            availability_zone=data["availability_zone"],
            key_name=data.get("key_name"),
            created=datetime.fromisoformat(data["created"]),
            updated=datetime.fromisoformat(data["updated"]),
            launched_at=(
                datetime.fromisoformat(data["launched_at"]) if data.get("launched_at") else None
            ),
            metadata=data.get("metadata", {}),
            addresses=data.get("addresses", {}),
            security_groups=data.get("security_groups", [{"name": "default"}]),
            admin_pass=data.get("admin_pass"),
        )

    def _dict_to_flavor(self, data: dict[str, Any]) -> Flavor:
        """Convert dictionary to Flavor object."""
        return Flavor(
            id=data["id"],
            name=data["name"],
            vcpus=data["vcpus"],
            ram=data["ram"],
            disk=data["disk"],
            ephemeral=data.get("ephemeral", 0),
            swap=data.get("swap", 0),
            is_public=data.get("is_public", True),
            description=data.get("description", ""),
        )

    def _dict_to_image(self, data: dict[str, Any]) -> Image:
        """Convert dictionary to Image object."""
        return Image(
            id=data["id"],
            name=data["name"],
            status=data["status"],
            min_disk=data.get("min_disk", 0),
            min_ram=data.get("min_ram", 0),
            size=data.get("size", 0),
            created=(
                datetime.fromisoformat(data["created"]) if "created" in data else datetime.utcnow()
            ),
            updated=(
                datetime.fromisoformat(data["updated"]) if "updated" in data else datetime.utcnow()
            ),
            metadata=data.get("metadata", {}),
        )

    def _dict_to_keypair(self, data: dict[str, Any]) -> Keypair:
        """Convert dictionary to Keypair object."""
        return Keypair(
            name=data["name"],
            public_key=data["public_key"],
            fingerprint=data["fingerprint"],
            user_id=data["user_id"],
            type=data.get("type", "ssh"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_domain(self, data: dict[str, Any]) -> Domain:
        """Convert dictionary to Domain object."""
        return Domain(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            tags=data.get("tags", []),
        )

    def _dict_to_project(self, data: dict[str, Any]) -> Project:
        """Convert dictionary to Project object."""
        return Project(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            domain_id=data.get("domain_id", "default"),
            parent_id=data.get("parent_id"),
            enabled=data.get("enabled", True),
            is_domain=data.get("is_domain", False),
            tags=data.get("tags", []),
            options=data.get("options", {}),
        )

    def _dict_to_user(self, data: dict[str, Any]) -> User:
        """Convert dictionary to User object."""
        return User(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            domain_id=data.get("domain_id", "default"),
            default_project_id=data.get("default_project_id"),
            enabled=data.get("enabled", True),
            password_hash=data.get("password_hash", ""),
            email=data.get("email", ""),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_role(self, data: dict[str, Any]) -> Role:
        """Convert dictionary to Role object."""
        return Role(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            domain_id=data.get("domain_id"),
        )

    def _dict_to_role_assignment(self, data: dict[str, Any]) -> RoleAssignment:
        """Convert dictionary to RoleAssignment object."""
        return RoleAssignment(
            role_id=data["role_id"],
            user_id=data.get("user_id"),
            group_id=data.get("group_id"),
            project_id=data.get("project_id"),
            domain_id=data.get("domain_id"),
            inherited=data.get("inherited", False),
        )

    def _dict_to_network(self, data: dict[str, Any]) -> Network:
        """Convert dictionary to Network object."""
        return Network(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            project_id=data["tenant_id"],
            admin_state_up=data.get("admin_state_up", True),
            status=NetworkStatus(data.get("status", "ACTIVE")),
            shared=data.get("shared", False),
            external=data.get("router:external", False),
            mtu=data.get("mtu", 1500),
            port_security_enabled=data.get("port_security_enabled", True),
            provider_network_type=data.get("provider:network_type"),
            provider_physical_network=data.get("provider:physical_network"),
            provider_segmentation_id=data.get("provider:segmentation_id"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_subnet(self, data: dict[str, Any]) -> Subnet:
        """Convert dictionary to Subnet object."""
        return Subnet(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            network_id=data["network_id"],
            project_id=data["tenant_id"],
            cidr=data["cidr"],
            gateway_ip=data.get("gateway_ip"),
            ip_version=data.get("ip_version", 4),
            enable_dhcp=data.get("enable_dhcp", True),
            dns_nameservers=data.get("dns_nameservers", []),
            allocation_pools=[
                AllocationPool(start=p["start"], end=p["end"])
                for p in data.get("allocation_pools", [])
            ],
            host_routes=data.get("host_routes", []),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_port(self, data: dict[str, Any]) -> Port:
        """Convert dictionary to Port object."""
        return Port(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            network_id=data["network_id"],
            project_id=data["tenant_id"],
            mac_address=data["mac_address"],
            admin_state_up=data.get("admin_state_up", True),
            status=PortStatus(data.get("status", "ACTIVE")),
            device_id=data.get("device_id", ""),
            device_owner=data.get("device_owner", ""),
            fixed_ips=[
                FixedIP(subnet_id=f["subnet_id"], ip_address=f["ip_address"])
                for f in data.get("fixed_ips", [])
            ],
            security_groups=data.get("security_groups", []),
            port_security_enabled=data.get("port_security_enabled", True),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_router(self, data: dict[str, Any]) -> Router:
        """Convert dictionary to Router object."""
        ext_gw = None
        if data.get("external_gateway_info"):
            gw_data = data["external_gateway_info"]
            ext_gw = ExternalGatewayInfo(
                network_id=gw_data["network_id"],
                enable_snat=gw_data.get("enable_snat", True),
                external_fixed_ips=[
                    FixedIP(subnet_id=f["subnet_id"], ip_address=f["ip_address"])
                    for f in gw_data.get("external_fixed_ips", [])
                ],
            )
        return Router(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            project_id=data["tenant_id"],
            admin_state_up=data.get("admin_state_up", True),
            status=RouterStatus(data.get("status", "ACTIVE")),
            external_gateway_info=ext_gw,
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_floating_ip(self, data: dict[str, Any]) -> FloatingIP:
        """Convert dictionary to FloatingIP object."""
        return FloatingIP(
            id=data["id"],
            floating_ip_address=data["floating_ip_address"],
            floating_network_id=data["floating_network_id"],
            router_id=data.get("router_id"),
            port_id=data.get("port_id"),
            fixed_ip_address=data.get("fixed_ip_address"),
            project_id=data["tenant_id"],
            status=FloatingIPStatus(data.get("status", "DOWN")),
            description=data.get("description", ""),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_security_group(self, data: dict[str, Any]) -> SecurityGroup:
        """Convert dictionary to SecurityGroup object."""
        return SecurityGroup(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            project_id=data["tenant_id"],
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_volume(self, data: dict[str, Any]) -> Volume:
        """Convert dictionary to Volume object."""
        return Volume(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            size=data["size"],
            status=VolumeStatus(data["status"]),
            availability_zone=data.get("availability_zone", "nova"),
            project_id=data["tenant_id"],
            user_id=data.get("user_id", ""),
            volume_type=data.get("volume_type", "lvmdriver-1"),
            bootable=data.get("bootable", False),
            encrypted=data.get("encrypted", False),
            multiattach=data.get("multiattach", False),
            source_volid=data.get("source_volid"),
            snapshot_id=data.get("snapshot_id"),
            image_id=data.get("image_id"),
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_snapshot(self, data: dict[str, Any]) -> Snapshot:
        """Convert dictionary to Snapshot object."""
        return Snapshot(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            volume_id=data["volume_id"],
            status=SnapshotStatus(data["status"]),
            size=data["size"],
            project_id=data["tenant_id"],
            user_id=data.get("user_id", ""),
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
        )

    def _dict_to_volume_type(self, data: dict[str, Any]) -> VolumeType:
        """Convert dictionary to VolumeType object."""
        return VolumeType(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            is_public=data.get("is_public", True),
            extra_specs=data.get("extra_specs", {}),
        )

    def _dict_to_glance_image(self, data: dict[str, Any]) -> GlanceImage:
        """Convert dictionary to GlanceImage object."""
        return GlanceImage(
            id=data["id"],
            name=data["name"],
            status=ImageStatus(data["status"]),
            visibility=ImageVisibility(data["visibility"]),
            protected=data.get("protected", False),
            owner=data.get("owner", ""),
            min_disk=data.get("min_disk", 0),
            min_ram=data.get("min_ram", 0),
            size=data.get("size"),
            virtual_size=data.get("virtual_size"),
            checksum=data.get("checksum"),
            os_hash_algo=data.get("os_hash_algo"),
            os_hash_value=data.get("os_hash_value"),
            os_hidden=data.get("os_hidden", False),
            container_format=(
                ContainerFormat(data["container_format"]) if data.get("container_format") else None
            ),
            disk_format=DiskFormat(data["disk_format"]) if data.get("disk_format") else None,
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.utcnow()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.utcnow()
            ),
            tags=data.get("tags", []),
            properties=data.get("properties", {}),
            architecture=data.get("architecture"),
            os_distro=data.get("os_distro"),
            os_version=data.get("os_version"),
        )

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
            if self.auto_save:
                self.save()
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
                if self.auto_save:
                    self.save()
            return domain

    def delete_domain(self, domain_id: str) -> bool:
        """Delete a domain."""
        with self._lock:
            if domain_id in self._domains and domain_id != "default":
                del self._domains[domain_id]
                if self.auto_save:
                    self.save()
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
        tags: list[str] | None = None,
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
                tags=list(tags or []),
            )
            self._projects[pid] = project
            if self.auto_save:
                self.save()
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
        tags: list[str] | None = None,
        tags_any: list[str] | None = None,
        not_tags: list[str] | None = None,
        not_tags_any: list[str] | None = None,
    ) -> list[Project]:
        """List projects with optional filtering.

        The four tag filters follow the Identity API: ``tags`` matches projects
        carrying *all* of the given tags, ``tags_any`` at least one, and the
        ``not_`` variants are their complements.
        """
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
            if tags:
                wanted = set(tags)
                projects = [p for p in projects if wanted.issubset(set(p.tags))]
            if tags_any:
                wanted = set(tags_any)
                projects = [p for p in projects if wanted & set(p.tags)]
            if not_tags:
                unwanted = set(not_tags)
                projects = [p for p in projects if not unwanted.issubset(set(p.tags))]
            if not_tags_any:
                unwanted = set(not_tags_any)
                projects = [p for p in projects if not (unwanted & set(p.tags))]
            return projects

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        domain_id: str | None = None,
        tags: list[str] | None = None,
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
                if tags is not None:
                    project.tags = list(dict.fromkeys(tags))
                if self.auto_save:
                    self.save()
            return project

    def add_project_tag(self, project_id: str, tag: str) -> Project | None:
        """Add a single tag to a project, ignoring duplicates."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            if tag not in project.tags:
                project.tags.append(tag)
                if self.auto_save:
                    self.save()
            return project

    def delete_project_tag(self, project_id: str, tag: str) -> bool:
        """Remove a single tag from a project. Returns False when absent."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None or tag not in project.tags:
                return False
            project.tags.remove(tag)
            if self.auto_save:
                self.save()
            return True

    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        with self._lock:
            if project_id in self._projects:
                del self._projects[project_id]
                # Remove associated role assignments
                self._role_assignments = [
                    ra for ra in self._role_assignments if ra.project_id != project_id
                ]
                if self.auto_save:
                    self.save()
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
            if self.auto_save:
                self.save()
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
                user.updated_at = datetime.now(timezone.utc)
                if self.auto_save:
                    self.save()
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
                if self.auto_save:
                    self.save()
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
            if self.auto_save:
                self.save()
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
                if self.auto_save:
                    self.save()
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
                if self.auto_save:
                    self.save()
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
            self._cinder_quotas.clear()
            self._cinder_quota_classes.clear()
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

            if self.auto_save:
                self.save()

            return volume

    def _complete_volume_creation(self, volume_id: str) -> None:
        """Simulate volume creation completion."""
        volume = self._volumes.get(volume_id)
        if volume:
            volume.status = VolumeStatus.AVAILABLE
            volume.updated_at = datetime.now(timezone.utc)

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
        """List volumes with optional filtering.

        ``project_id`` is the resolved scope: the caller decides whether the
        request may cross a project boundary and passes None for "every
        project". ``all_tenants`` is kept only so existing callers keep working;
        it widens the scope but never narrows it.
        """
        with self._lock:
            volumes = list(self._volumes.values())

            # Apply filters
            if project_id:
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
            volume.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
                volume.updated_at = datetime.now(timezone.utc)
                if self.auto_save:
                    self.save()
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
            volume.updated_at = datetime.now(timezone.utc)

            if self.auto_save:
                self.save()

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
                    volume.updated_at = datetime.now(timezone.utc)
                    if self.auto_save:
                        self.save()
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
            volume.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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

            if self.auto_save:
                self.save()

            return snapshot

    def _complete_snapshot_creation(self, snapshot_id: str) -> None:
        """Simulate snapshot creation completion."""
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot:
            snapshot.status = SnapshotStatus.AVAILABLE
            snapshot.progress = "100%"
            snapshot.updated_at = datetime.now(timezone.utc)

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
            snapshot.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
                if self.auto_save:
                    self.save()
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
            # Nova serves images from its own store, so an image that only lands
            # in Glance cannot be booted from. The seeded images are mirrored the
            # same way; anything created later has to be too.
            self._images[image.id] = image.to_nova_image()
            self._image_members[image.id] = []
            if self.auto_save:
                self.save()
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

            image.updated_at = datetime.now(timezone.utc)

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
            image.updated_at = datetime.now(timezone.utc)
            del self._glance_images[image_id]

            if self.auto_save:
                self.save()

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
            image.updated_at = datetime.now(timezone.utc)

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
            image.updated_at = datetime.now(timezone.utc)

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
            image.updated_at = datetime.now(timezone.utc)

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
                image.updated_at = datetime.now(timezone.utc)
            return True

    def delete_image_tag(self, image_id: str, tag: str) -> bool:
        """Delete a tag from an image."""
        with self._lock:
            image = self._glance_images.get(image_id)
            if not image:
                return False

            if tag in image.tags:
                image.tags.remove(tag)
                image.updated_at = datetime.now(timezone.utc)
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
                    member.updated_at = datetime.now(timezone.utc)
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
            id=default_resource_id("network:external"),
            name="external",
            description="External network for floating IPs",
            external=True,
            shared=True,
            project_id="admin",
        )
        self._networks[ext_network.id] = ext_network

        # Create external subnet
        ext_subnet = Subnet(
            id=default_resource_id("subnet:external-subnet"),
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
            id=default_resource_id("network:private"),
            name="private",
            description="Default private network",
            project_id="admin",
            shared=True,  # Shared so all projects can see/use it
        )
        self._networks[private_network.id] = private_network

        # Create private subnet
        private_subnet = Subnet(
            id=default_resource_id("subnet:private-subnet"),
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

    def _find_subnet_for_ip(self, network: Network, ip: str) -> Subnet | None:
        """Return the network's subnet whose CIDR contains ``ip``, if any."""
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        for subnet_id in network.subnets:
            subnet = self._subnets.get(subnet_id)
            if subnet is None or not subnet.cidr:
                continue
            try:
                if address in ipaddress.ip_network(subnet.cidr, strict=False):
                    return subnet
            except ValueError:
                continue
        return None

    def _is_fixed_ip_in_use(self, network_id: str, ip: str) -> bool:
        """Check whether any port on the network already holds ``ip``."""
        return any(
            fixed_ip.ip_address == ip
            for port in self._ports.values()
            if port.network_id == network_id
            for fixed_ip in port.fixed_ips
        )

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
            if self.auto_save:
                self.save()
            return network

    def _network_rbac_targets(
        self,
        network_id: str,
        project_id: str | None,
        actions: tuple[str, ...] | None = None,
    ) -> bool:
        """Whether an RBAC policy grants the project access to the network.

        A policy matches when it targets the project explicitly or all
        tenants (``target_project == "*"``). When ``actions`` is given, only
        policies with one of those actions are considered.
        """
        if project_id is None:
            return False
        with self._lock:
            for policy in self._rbac_policies.values():
                if policy.object_type != "network" or policy.object_id != network_id:
                    continue
                if actions is not None and policy.action not in actions:
                    continue
                if policy.target_project in ("*", project_id):
                    return True
        return False

    def _network_visible_to(self, network: Network, project_id: str | None) -> bool:
        """Whether a network is visible to the given project.

        Visible when owned by the project, globally shared/external, or shared
        to the project (or all tenants) through any RBAC policy.
        """
        if project_id is None:
            return True
        if network.project_id == project_id or network.shared or network.external:
            return True
        return self._network_rbac_targets(network.id, project_id)

    def is_network_external_for(self, network_id: str, project_id: str | None) -> bool:
        """Whether a network may be used as an external gateway by the project.

        True for globally external networks, or for networks shared to the
        project (or all tenants) via an ``access_as_external`` RBAC policy.
        """
        with self._lock:
            network = self._networks.get(network_id)
            if network is None:
                return False
            if network.external:
                return True
            return self._network_rbac_targets(
                network_id, project_id, actions=("access_as_external",)
            )

    def get_network(self, network_id: str, project_id: str | None = None) -> Network | None:
        """Get a network by ID.

        Args:
            network_id: The network ID to look up.
            project_id: If provided, verify access (shared/external networks
                        and RBAC-shared networks are accessible).

        Returns:
            The network if found and accessible, else None.
        """
        with self._lock:
            network = self._networks.get(network_id)
            if network is None:
                return None
            if not self._network_visible_to(network, project_id):
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
        """List networks with optional filtering.

        Networks shared to the project through RBAC policies are included, and
        the ``external`` filter is evaluated per-project so that networks shared
        as external via an ``access_as_external`` RBAC policy are returned to the
        target tenant.
        """
        with self._lock:
            networks = list(self._networks.values())
            if project_id:
                networks = [n for n in networks if self._network_visible_to(n, project_id)]
            if name:
                networks = [n for n in networks if n.name == name]
            if shared is not None:
                networks = [n for n in networks if n.shared == shared]
            if external is not None:
                if project_id:
                    networks = [
                        n
                        for n in networks
                        if self.is_network_external_for(n.id, project_id) == external
                    ]
                else:
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
            network.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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

            # Neutron always gives a subnet an allocation pool, derived from the
            # CIDR minus the network address and the gateway, so ports created
            # on it get an address. Without one nothing here ever allocated, and
            # every port came back with an empty ip_address.
            if not pools:
                network_obj = ipaddress.ip_network(cidr, strict=False)
                hosts = list(network_obj.hosts())
                if hosts:
                    first = hosts[0]
                    if str(first) == gateway_ip and len(hosts) > 1:
                        first = hosts[1]
                    pools = [AllocationPool(start=str(first), end=str(hosts[-1]))]

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
            if self.auto_save:
                self.save()
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
            subnet.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
        validate_fixed_ips: bool = False,
    ) -> Port | None:
        """Create a new port.

        With ``validate_fixed_ips`` (Neutron/Nova user-facing paths), each
        explicit IP must fall inside a subnet CIDR of the network and be free,
        and its ``subnet_id`` is resolved from the CIDR when not supplied.
        Internal callers (e.g. router interfaces binding the gateway IP) skip
        validation.

        Raises:
            InvalidFixedIPError: If a validated IP is in no subnet of the network.
            FixedIPAlreadyInUseError: If a validated IP is held by another port.
        """
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
                    subnet_id = fip.get("subnet_id", "")
                    ip_address = fip.get("ip_address", "")
                    if validate_fixed_ips and ip_address:
                        subnet = self._find_subnet_for_ip(network, ip_address)
                        if subnet is None:
                            raise InvalidFixedIPError(ip_address, network_id)
                        if self._is_fixed_ip_in_use(network_id, ip_address):
                            raise FixedIPAlreadyInUseError(ip_address, network_id)
                        if not subnet_id:
                            subnet_id = subnet.id
                    if not ip_address and subnet_id:
                        # Asking for a subnet without naming an address is a
                        # request for Neutron to pick one; it does not mean "no
                        # address". This is the shape clients use when they want
                        # a port on a particular subnet.
                        subnet = self._subnets.get(subnet_id)
                        if subnet is not None:
                            ip_address = self._allocate_ip_from_subnet(subnet) or ""
                    port_fixed_ips.append(FixedIP(subnet_id=subnet_id, ip_address=ip_address))
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
            if self.auto_save:
                self.save()
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
        fixed_ips: list[str] | None = None,
    ) -> list[Port]:
        """List ports with optional filtering.

        ``fixed_ips`` is the Neutron-style list of ``key=value`` filters (e.g.
        ``["subnet_id=<id>", "ip_address=<ip>"]``); a port matches when, for each
        filter, it has a fixed IP whose attribute equals the value.
        """
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
            if fixed_ips:
                criteria = [
                    (k.strip(), v.strip())
                    for f in fixed_ips
                    if "=" in f
                    for k, _, v in [f.partition("=")]
                ]
                ports = [
                    p
                    for p in ports
                    if all(
                        any(getattr(ip, key, None) == value for ip in p.fixed_ips)
                        for key, value in criteria
                    )
                ]
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
            port.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
            return True

    # Router operations
    def _build_external_gateway_info(
        self,
        external_gateway_info: dict[str, Any] | None,
        router_id: str,
    ) -> ExternalGatewayInfo | None:
        """Build an ExternalGatewayInfo from a request payload.

        Setting a gateway is backed by a real port, as in Neutron: l3_db's
        ``_create_router_gw_port`` always creates one with device_owner
        ``network:router_gateway`` and device_id set to the router, passing
        ``fixed_ips or ATTR_NOT_SPECIFIED`` so IPAM allocates an address from
        the external network's subnet when the caller named none. Clients read
        the result back out of external_fixed_ips — Waldur indexes
        ``external_fixed_ips[0]`` right after the call — so an empty list makes
        the router look gateway-less to them.

        Neutron keeps that port stable: ``_update_router_gw_info`` only touches
        it when the requested IPs actually differ or the network changed, so
        re-sending the same gateway is idempotent and does not re-allocate.

        Returns None when the payload is empty, which is how a gateway is
        cleared.
        """
        if not external_gateway_info:
            self._release_router_gateway_port(router_id)
            return None

        network_id = external_gateway_info.get("network_id", "")
        requested_ips = [
            FixedIP(
                subnet_id=f.get("subnet_id", ""),
                ip_address=f.get("ip_address", ""),
            )
            for f in external_gateway_info.get("external_fixed_ips", [])
        ]

        # Idempotence: an unchanged request keeps the existing port and its
        # address. Neutron decides this in _check_for_external_ip_change, which
        # treats "no external_fixed_ips supplied" as "no change requested".
        current = self._get_router_gateway_port(router_id)
        if current is not None and current.network_id == network_id:
            if not requested_ips or self._same_fixed_ips(current.fixed_ips, requested_ips):
                return ExternalGatewayInfo(
                    network_id=network_id,
                    enable_snat=external_gateway_info.get("enable_snat", True),
                    external_fixed_ips=list(current.fixed_ips),
                )

        self._release_router_gateway_port(router_id)

        network = self._networks.get(network_id)
        fixed_ips = requested_ips
        if fixed_ips:
            # Pair each requested address with the subnet that contains it.
            # _allocate_ip_from_subnet keys its used-address set on subnet_id, so
            # an unresolved one leaves the address invisible to the allocator and
            # it can be handed out a second time.
            if network:
                fixed_ips = [
                    self._resolve_fixed_ip_subnet(network, fixed_ip) for fixed_ip in fixed_ips
                ]
        else:
            subnet = None
            if network:
                subnet = next(
                    (
                        self._subnets[subnet_id]
                        for subnet_id in network.subnets
                        if subnet_id in self._subnets
                    ),
                    None,
                )
            if subnet:
                ip_address = self._allocate_ip_from_subnet(subnet)
                if not ip_address:
                    # A subnet exists but has nothing left. Neutron surfaces this
                    # as IpAddressGenerationFailure (409) from IPAM and the
                    # gateway is not set. Only a network with no subnets at all
                    # yields a gateway port with no address - see below.
                    raise IpAddressGenerationFailureError(network_id)
                fixed_ips = [FixedIP(subnet_id=subnet.id, ip_address=ip_address)]
            # No subnet at all: fall through with an empty fixed_ips. Neutron
            # calls this "not an error" (Subnet.network_has_no_subnet) and
            # _create_router_gw_port merely logs "No IPs available for external
            # network", leaving the gateway set with external_fixed_ips: [].

        # The port is created either way, so an explicitly requested address is
        # accounted for and cannot later be handed out to something else.
        # Neutron leaves project_id unset ("Port has no 'project-id', as it is
        # hidden from user"), which also keeps it out of tenant port listings.
        gateway_port = Port(
            id=str(uuid4()),
            name="",
            description="",
            network_id=network_id,
            admin_state_up=True,
            mac_address=self._generate_mac_address(),
            fixed_ips=list(fixed_ips),
            device_id=router_id,
            device_owner=DEVICE_OWNER_ROUTER_GATEWAY,
            project_id="",
            security_groups=[],
            port_security_enabled=False,
        )
        self._ports[gateway_port.id] = gateway_port

        return ExternalGatewayInfo(
            network_id=network_id,
            enable_snat=external_gateway_info.get("enable_snat", True),
            external_fixed_ips=fixed_ips,
        )

    def _resolve_fixed_ip_subnet(self, network: Network, fixed_ip: FixedIP) -> FixedIP:
        """Fill in a requested fixed IP's subnet_id from its address."""
        if fixed_ip.subnet_id or not fixed_ip.ip_address:
            return fixed_ip
        subnet = self._find_subnet_for_ip(network, fixed_ip.ip_address)
        if subnet is None:
            return fixed_ip
        return FixedIP(subnet_id=subnet.id, ip_address=fixed_ip.ip_address)

    @staticmethod
    def _same_fixed_ips(current: list[FixedIP], requested: list[FixedIP]) -> bool:
        """Compare fixed IPs the way Neutron's change detection does.

        Only the fields the caller actually specified take part: a request that
        names subnets but no addresses must not count as a change just because
        the allocated addresses are filled in on our side.
        """
        requested_subnets = {ip.subnet_id for ip in requested if ip.subnet_id}
        if requested_subnets and requested_subnets != {ip.subnet_id for ip in current}:
            return False
        requested_addresses = {ip.ip_address for ip in requested if ip.ip_address}
        if requested_addresses and requested_addresses != {ip.ip_address for ip in current}:
            return False
        return True

    def _get_router_gateway_port(self, router_id: str) -> Port | None:
        """Return the gateway port belonging to ``router_id``, if any."""
        return next(
            (
                port
                for port in self._ports.values()
                if port.device_id == router_id and port.device_owner == DEVICE_OWNER_ROUTER_GATEWAY
            ),
            None,
        )

    def _release_router_gateway_port(self, router_id: str) -> None:
        """Drop any gateway port previously created for ``router_id``.

        Keeps the allocation pool from leaking addresses when a gateway is
        replaced or cleared.
        """
        stale = [
            port_id
            for port_id, port in self._ports.items()
            if port.device_id == router_id and port.device_owner == DEVICE_OWNER_ROUTER_GATEWAY
        ]
        for port_id in stale:
            del self._ports[port_id]

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
            router_id = str(uuid4())
            ext_gateway = self._build_external_gateway_info(external_gateway_info, router_id)

            router = Router(
                id=router_id,
                name=name,
                description=description,
                project_id=project_id,
                admin_state_up=admin_state_up,
                external_gateway_info=ext_gateway,
            )
            self._routers[router.id] = router
            if self.auto_save:
                self.save()
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
                router.external_gateway_info = self._build_external_gateway_info(
                    external_gateway_info, router.id
                )
            if routes is not None:
                router.routes = routes
            router.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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

            result = {
                "id": router_id,
                "subnet_id": subnet_id,
                "port_id": port_id,
                "tenant_id": router.project_id,
            }
            if self.auto_save:
                self.save()
            return result

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

            result = {
                "id": router_id,
                "subnet_id": subnet_id,
                "port_id": port_id,
                "tenant_id": router.project_id,
            }
            if self.auto_save:
                self.save()
            return result

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
        """Create a new floating IP.

        In real OpenStack Neutron, creating a floating IP also creates a port
        on the external network with device_owner='network:floatingip'. This
        port holds the floating IP address and is referenced via floating_port_id.
        """
        with self._lock:
            network = self._networks.get(floating_network_id)
            # is_network_external_for, not network.external: a network shared
            # through an access_as_external RBAC policy is a valid floating-IP
            # network, exactly as it is a valid router gateway. Checking the flag
            # directly made those two disagree.
            if not network or not self.is_network_external_for(floating_network_id, project_id):
                return None

            # Allocate from the external network's own subnet, the way Neutron
            # does. Falling back to a hardcoded 203.0.113.x counter would hand
            # out addresses off the wrong network entirely once a preset defines
            # an external network with a different CIDR, and would start at .1 -
            # the subnet's gateway - rather than inside the allocation pool.
            if not floating_ip_address:
                for sid in network.subnets:
                    external_subnet = self._subnets.get(sid)
                    if external_subnet is None:
                        continue
                    floating_ip_address = self._allocate_ip_from_subnet(external_subnet)
                    if floating_ip_address:
                        break
                if not floating_ip_address:
                    # No subnet, or every pool is full. Neutron reports this as
                    # IpAddressGenerationFailure (409) / ExternalIpAddressExhausted,
                    # not as a missing network, and clients rely on telling the
                    # two apart - so don't fold it into the None that the caller
                    # renders as "external network not found".
                    raise IpAddressGenerationFailureError(floating_network_id)

            # Create floating IP ID first (needed for port device_id)
            fip_id = str(uuid4())

            # Pair the address with the subnet that actually contains it. Taking
            # the network's first subnet mislabels the port on a multi-subnet
            # external network, and _allocate_ip_from_subnet keys its used-address
            # set on subnet_id - so a wrong or empty one lets the address be
            # handed out a second time.
            subnet = self._find_subnet_for_ip(network, floating_ip_address)
            subnet_id = subnet.id if subnet else None

            # Create a port on the external network to hold the floating IP
            # This mimics real Neutron behavior where a port with
            # device_owner='network:floatingip' is created
            floating_port = Port(
                id=str(uuid4()),
                name="",
                description="",
                network_id=floating_network_id,
                admin_state_up=True,
                mac_address=self._generate_mac_address(),
                fixed_ips=(
                    [FixedIP(subnet_id=subnet_id or "", ip_address=floating_ip_address)]
                    if subnet_id
                    else []
                ),
                # Neutron sets device_id to the literal "PENDING" here and only
                # rewrites it to the floating IP's id after the record commits,
                # so a crash in between leaves a port its janitor can reap
                # (_get_dead_floating_port_candidates). We create both under one
                # lock, so that window cannot open and the sentinel would be a
                # state nothing could ever observe.
                device_id=fip_id,
                device_owner=DEVICE_OWNER_FLOATINGIP,
                # Neutron: "This external port is never exposed to the project.
                # it is used purely for internal system and admin use when
                # managing floating IPs." Leaving it project-less keeps it out of
                # tenant port listings, as in a real cloud.
                project_id="",
                security_groups=[],
                port_security_enabled=False,  # Floating IP ports don't have port security
            )
            self._ports[floating_port.id] = floating_port

            fip = FloatingIP(
                id=fip_id,
                description=description,
                floating_network_id=floating_network_id,
                floating_ip_address=floating_ip_address,
                port_id=port_id,
                floating_port_id=floating_port.id,  # Reference to external network port
                fixed_ip_address=fixed_ip_address,
                project_id=project_id,
            )

            if port_id:
                fip.status = FloatingIPStatus.ACTIVE
                internal_port = self._ports.get(port_id)
                if internal_port and internal_port.fixed_ips:
                    fip.fixed_ip_address = internal_port.fixed_ips[0].ip_address

            self._floating_ips[fip.id] = fip
            if self.auto_save:
                self.save()
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
            fip.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
            return fip

    def delete_floating_ip(self, floatingip_id: str, project_id: str | None = None) -> bool:
        """Delete a floating IP and its associated external network port.

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

            # Delete the associated port on the external network
            if fip.floating_port_id and fip.floating_port_id in self._ports:
                del self._ports[fip.floating_port_id]

            del self._floating_ips[floatingip_id]
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            sg.updated_at = datetime.now(timezone.utc)
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            if self.auto_save:
                self.save()
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
            self._rbac_policies.clear()
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

    def get_nova_quota_class(self, class_name: str = "default") -> NovaQuota:
        """Get a Nova quota class, creating it from the defaults if unseen."""
        with self._lock:
            if class_name not in self._nova_quota_classes:
                self._nova_quota_classes[class_name] = NovaQuota(project_id=class_name)
            return self._nova_quota_classes[class_name]

    def update_nova_quota_class(self, class_name: str, limits: dict[str, int]) -> NovaQuota:
        """Update a Nova quota class from a flat mapping of limits."""
        with self._lock:
            quota = self.get_nova_quota_class(class_name)
            for key, value in limits.items():
                if hasattr(quota, key) and key != "project_id":
                    setattr(quota, key, value)
            if self.auto_save:
                self.save()
            return quota

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
        per_type: dict[str, int] | None = None,
    ) -> CinderQuota:
        """Update Cinder quotas for a project.

        Args:
            per_type: ``<metric>_<volume type>`` limits to merge in. Keys absent
                from the mapping are left untouched, matching how a Cinder quota
                update only carries the keys being changed.
        """
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
            if per_type:
                quota.per_type.update(per_type)
            return quota

    def get_cinder_quota_limits(self, project_id: str) -> dict[str, int]:
        """Every Cinder quota limit for a project, including per-volume-type keys.

        Cinder derives one quota resource per metric for every volume type that
        exists, so those keys are always present in a quota set even when they
        were never set explicitly; they fall back to the corresponding global
        default. Reproduced here so a client reading a quota set sees the same
        key set it would from a real Cinder.
        """
        with self._lock:
            quota = self.get_cinder_quota(project_id)
            limits = quota.limits()
            for vtype in self._volume_types.values():
                for metric in CinderQuota.PER_TYPE_METRICS:
                    key = f"{metric}_{vtype.name}"
                    if key not in limits:
                        limits[key] = getattr(quota, metric)
            return limits

    def get_cinder_quota_class(self, class_name: str = "default") -> CinderQuota:
        """Get a Cinder quota class, creating it from the defaults if unseen."""
        with self._lock:
            if class_name not in self._cinder_quota_classes:
                self._cinder_quota_classes[class_name] = CinderQuota(project_id=class_name)
            return self._cinder_quota_classes[class_name]

    def update_cinder_quota_class(self, class_name: str, limits: dict[str, int]) -> CinderQuota:
        """Update a Cinder quota class from a flat mapping of limits."""
        with self._lock:
            quota = self.get_cinder_quota_class(class_name)
            for key, value in limits.items():
                if hasattr(quota, key) and key != "project_id":
                    setattr(quota, key, value)
                else:
                    quota.per_type[key] = value
            if self.auto_save:
                self.save()
            return quota

    def delete_cinder_quota(self, project_id: str) -> bool:
        """Delete Cinder quota for a project (resets to defaults)."""
        with self._lock:
            if project_id in self._cinder_quotas:
                del self._cinder_quotas[project_id]
                return True
            return False

    def get_cinder_quota_usage(self, project_id: str) -> dict[str, int]:
        """Get current Cinder quota usage for a project.

        Includes the ``<metric>_<volume type>`` keys alongside the totals, so a
        quota set requested with ``usage=true`` can report per-volume-type
        consumption the same way Cinder does.
        """
        with self._lock:
            volumes = [v for v in self._volumes.values() if v.project_id == project_id]
            snapshots = [s for s in self._snapshots.values() if s.project_id == project_id]
            total_gigabytes = sum(v.size for v in volumes)

            usage = {
                "volumes": len(volumes),
                "snapshots": len(snapshots),
                "gigabytes": total_gigabytes,
                "backups": 0,
                "backup_gigabytes": 0,
                "groups": 0,
            }

            volumes_by_id = {v.id: v for v in volumes}
            for vtype in self._volume_types.values():
                typed = [v for v in volumes if v.volume_type == vtype.name]
                typed_snapshots = [
                    s
                    for s in snapshots
                    if volumes_by_id.get(s.volume_id) is not None
                    and volumes_by_id[s.volume_id].volume_type == vtype.name
                ]
                usage[f"volumes_{vtype.name}"] = len(typed)
                usage[f"gigabytes_{vtype.name}"] = sum(v.size for v in typed)
                usage[f"snapshots_{vtype.name}"] = len(typed_snapshots)

            return usage

    # ==================== OpenID Provider Operations ====================

    def create_oidc_client(
        self,
        client_id: str,
        client_secret: str = "",
        redirect_uris: list[str] | None = None,
        grant_types: list[str] | None = None,
    ) -> OidcClient:
        """Register a relying party with the embedded OpenID Provider."""
        with self._lock:
            client = OidcClient(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uris=list(redirect_uris or []),
                **({"grant_types": list(grant_types)} if grant_types else {}),
            )
            self._oidc_clients[client_id] = client
            if self.auto_save:
                self.save()
            return client

    def get_oidc_client(self, client_id: str) -> OidcClient | None:
        """Get a registered relying party."""
        with self._lock:
            return self._oidc_clients.get(client_id)

    def create_oidc_user(
        self,
        username: str,
        password: str = "",
        email: str = "",
        name: str = "",
        groups: list[str] | None = None,
        claims: dict[str, str] | None = None,
        subject: str | None = None,
    ) -> OidcUser:
        """Create an end user the OpenID Provider can authenticate."""
        with self._lock:
            user = OidcUser(
                username=username,
                password=password,
                email=email,
                name=name,
                groups=list(groups or []),
                claims=dict(claims or {}),
                **({"subject": subject} if subject else {}),
            )
            self._oidc_users[username] = user
            if self.auto_save:
                self.save()
            return user

    def get_oidc_user(self, username: str) -> OidcUser | None:
        """Get an OpenID Provider end user by username."""
        with self._lock:
            return self._oidc_users.get(username)

    def list_oidc_clients(self) -> list[OidcClient]:
        """List registered relying parties."""
        with self._lock:
            return sorted(self._oidc_clients.values(), key=lambda c: c.client_id)

    def list_oidc_users(self) -> list[OidcUser]:
        """List the end users the OpenID Provider can authenticate."""
        with self._lock:
            return sorted(self._oidc_users.values(), key=lambda u: u.username)

    def list_all_federation_protocols(self) -> list[FederationProtocol]:
        """List protocols across every identity provider."""
        with self._lock:
            return sorted(
                self._federation_protocols.values(),
                key=lambda p: (p.identity_provider_id, p.id),
            )

    def get_oidc_user_by_subject(self, subject: str) -> OidcUser | None:
        """Get an OpenID Provider end user by its stable subject identifier."""
        with self._lock:
            for user in self._oidc_users.values():
                if user.subject == subject:
                    return user
            return None

    def create_oidc_code(
        self, client_id: str, username: str, redirect_uri: str, scope: str
    ) -> OidcAuthorizationCode:
        """Issue a short-lived authorization code."""
        with self._lock:
            record = OidcAuthorizationCode(
                client_id=client_id,
                username=username,
                redirect_uri=redirect_uri,
                scope=scope,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            self._oidc_codes[record.code] = record
            return record

    def consume_oidc_code(self, code: str) -> OidcAuthorizationCode | None:
        """Redeem an authorization code. Codes are single use, as in OAuth 2."""
        with self._lock:
            record = self._oidc_codes.pop(code, None)
            if record is None:
                return None
            if record.expires_at and record.expires_at <= datetime.now(timezone.utc):
                return None
            return record

    def reset_oidc(self) -> None:
        """Reset all OpenID Provider data."""
        with self._lock:
            self._oidc_clients.clear()
            self._oidc_users.clear()
            self._oidc_codes.clear()

    # ==================== Swift Object Storage Operations ====================

    @staticmethod
    def _container_key(account: str, container: str) -> str:
        return f"{account}/{container}"

    @staticmethod
    def _object_key(account: str, container: str, name: str) -> str:
        return f"{account}/{container}/{name}"

    def get_swift_account(self, account: str, create: bool = True) -> SwiftAccount | None:
        """Get a Swift account, optionally creating it on first reference.

        Swift auto-creates an account the first time an authenticated request
        touches it, so ``create`` defaults to True.
        """
        with self._lock:
            existing = self._swift_accounts.get(account)
            if existing is not None:
                return existing
            if not create:
                return None
            project_id = account[len("AUTH_") :] if account.startswith("AUTH_") else account
            record = SwiftAccount(name=account, project_id=project_id)
            self._swift_accounts[account] = record
            if self.auto_save:
                self.save()
            return record

    def update_swift_account(
        self,
        account: str,
        metadata: dict[str, str] | None = None,
        sysmeta: dict[str, str] | None = None,
    ) -> SwiftAccount:
        """Merge metadata into a Swift account.

        An empty value removes the key, matching how Swift treats a metadata
        header sent with an empty body.
        """
        with self._lock:
            record = self.get_swift_account(account)
            assert record is not None  # noqa: S101 - create=True never returns None
            for source, target in ((metadata, record.metadata), (sysmeta, record.sysmeta)):
                for key, value in (source or {}).items():
                    if value == "":
                        target.pop(key, None)
                    else:
                        target[key] = value
            if self.auto_save:
                self.save()
            return record

    def list_swift_accounts(self) -> list[SwiftAccount]:
        """List every Swift account the emulator has seen."""
        with self._lock:
            return sorted(self._swift_accounts.values(), key=lambda a: a.name)

    def list_swift_containers(self, account: str | None = None) -> list[SwiftContainer]:
        """List containers, ordered by name as Swift does.

        With no account, lists across every account — which the API layer never
        does, but the status dashboard needs to show the whole cloud.
        """
        with self._lock:
            containers = [
                c
                for c in self._swift_containers.values()
                if account is None or c.account == account
            ]
            containers.sort(key=lambda c: (c.account, c.name))
            return containers

    def get_swift_container(self, account: str, container: str) -> SwiftContainer | None:
        """Get a container by account and name."""
        with self._lock:
            return self._swift_containers.get(self._container_key(account, container))

    def create_swift_container(
        self, account: str, container: str, metadata: dict[str, str] | None = None
    ) -> tuple[SwiftContainer, bool]:
        """Create a container, or merge metadata into an existing one.

        Returns the container and whether it was newly created, so the caller
        can answer 201 versus 202 the way Swift does.
        """
        with self._lock:
            self.get_swift_account(account)
            key = self._container_key(account, container)
            existing = self._swift_containers.get(key)
            if existing is not None:
                existing.metadata.update(metadata or {})
                if self.auto_save:
                    self.save()
                return existing, False
            record = SwiftContainer(name=container, account=account, metadata=dict(metadata or {}))
            self._swift_containers[key] = record
            if self.auto_save:
                self.save()
            return record, True

    def delete_swift_container(self, account: str, container: str) -> bool:
        """Delete an empty container. Returns False when it does not exist."""
        with self._lock:
            key = self._container_key(account, container)
            if key not in self._swift_containers:
                return False
            del self._swift_containers[key]
            if self.auto_save:
                self.save()
            return True

    def list_swift_objects(
        self,
        account: str | None = None,
        container: str | None = None,
        prefix: str | None = None,
    ) -> list[SwiftObject]:
        """List objects, ordered by name as Swift does.

        With no account or container, lists across the whole cloud, which the
        API layer never does but the status dashboard needs.
        """
        with self._lock:
            objects = [
                o
                for o in self._swift_objects.values()
                if (account is None or o.account == account)
                and (container is None or o.container == container)
            ]
            if prefix:
                objects = [o for o in objects if o.name.startswith(prefix)]
            objects.sort(key=lambda o: o.name)
            return objects

    def get_swift_object(self, account: str, container: str, name: str) -> SwiftObject | None:
        """Get an object by account, container and name."""
        with self._lock:
            return self._swift_objects.get(self._object_key(account, container, name))

    def put_swift_object(
        self,
        account: str,
        container: str,
        name: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> SwiftObject:
        """Store an object, replacing any existing one at the same path."""
        import base64
        import hashlib

        with self._lock:
            record = SwiftObject(
                name=name,
                container=container,
                account=account,
                content_type=content_type,
                size=len(content),
                etag=hashlib.md5(content, usedforsecurity=False).hexdigest(),
                content_b64=base64.b64encode(content).decode("ascii"),
                metadata=dict(metadata or {}),
            )
            self._swift_objects[self._object_key(account, container, name)] = record
            if self.auto_save:
                self.save()
            return record

    def delete_swift_object(self, account: str, container: str, name: str) -> bool:
        """Delete an object. Returns False when it does not exist."""
        with self._lock:
            key = self._object_key(account, container, name)
            if key not in self._swift_objects:
                return False
            del self._swift_objects[key]
            if self.auto_save:
                self.save()
            return True

    def get_swift_account_usage(self, account: str) -> dict[str, int]:
        """Total container count, object count and bytes stored in an account."""
        with self._lock:
            containers = [c for c in self._swift_containers.values() if c.account == account]
            objects = [o for o in self._swift_objects.values() if o.account == account]
            return {
                "container_count": len(containers),
                "object_count": len(objects),
                "bytes_used": sum(o.size for o in objects),
            }

    def get_swift_container_usage(self, account: str, container: str) -> dict[str, int]:
        """Object count and bytes stored in a container."""
        with self._lock:
            objects = [
                o
                for o in self._swift_objects.values()
                if o.account == account and o.container == container
            ]
            return {
                "object_count": len(objects),
                "bytes_used": sum(o.size for o in objects),
            }

    def reset_swift(self) -> None:
        """Reset all Swift data."""
        with self._lock:
            self._swift_accounts.clear()
            self._swift_containers.clear()
            self._swift_objects.clear()

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
                policy.updated_at = datetime.now(timezone.utc)

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

    def _compute_compute_usage(self) -> dict[str, int]:
        """Sum VCPU/RAM/DISK consumption across running servers.

        Caller must hold self._lock.
        """
        vcpus_used = 0
        memory_mb_used = 0
        disk_gb_used = 0
        running = 0
        for server in self._servers.values():
            if server.status != ServerStatus.ACTIVE:
                continue
            running += 1
            flavor = self._flavors.get(server.flavor_id)
            if flavor:
                vcpus_used += flavor.vcpus
                memory_mb_used += flavor.ram
                disk_gb_used += flavor.disk
        return {
            "vcpus_used": vcpus_used,
            "memory_mb_used": memory_mb_used,
            "disk_gb_used": disk_gb_used,
            "running_vms": running,
        }

    def get_hypervisor_statistics(self) -> dict[str, Any]:
        """Calculate dynamic hypervisor statistics based on current resources."""
        with self._lock:
            usage = self._compute_compute_usage()
            provider = self._get_default_resource_provider_locked()
            total_vcpus = provider.total_vcpus
            total_memory_mb = provider.total_memory_mb
            total_local_gb = provider.total_disk_gb

            return {
                "count": 1,  # Number of hypervisors
                "vcpus": total_vcpus,
                "vcpus_used": usage["vcpus_used"],
                "memory_mb": total_memory_mb,
                "memory_mb_used": usage["memory_mb_used"],
                "local_gb": total_local_gb,
                "local_gb_used": usage["disk_gb_used"],
                "free_ram_mb": total_memory_mb - usage["memory_mb_used"],
                "free_disk_gb": total_local_gb - usage["disk_gb_used"],
                "current_workload": 0,  # OpenStack concept - can remain 0
                "running_vms": usage["running_vms"],
                "disk_available_least": total_local_gb - usage["disk_gb_used"],
            }

    # ==================== Placement (resource providers) ====================

    def _init_default_resource_providers(self) -> None:
        """Seed one resource provider that mirrors the default hypervisor."""
        if self._resource_providers:
            return
        provider = ResourceProvider(
            name="compute-host-1",
            generation=0,
        )
        provider.root_provider_uuid = provider.uuid
        self._resource_providers[provider.uuid] = provider

    def _get_default_resource_provider_locked(self) -> ResourceProvider:
        """Return the seeded provider, recreating it if missing.

        Caller must hold self._lock.
        """
        if not self._resource_providers:
            provider = ResourceProvider(name="compute-host-1", generation=0)
            provider.root_provider_uuid = provider.uuid
            self._resource_providers[provider.uuid] = provider
        return next(iter(self._resource_providers.values()))

    def list_resource_providers(
        self,
        name: str | None = None,
        uuid: str | None = None,
    ) -> list[ResourceProvider]:
        """List resource providers, optionally filtered by name or uuid."""
        with self._lock:
            providers = list(self._resource_providers.values())
            if name is not None:
                providers = [p for p in providers if p.name == name]
            if uuid is not None:
                providers = [p for p in providers if p.uuid == uuid]
            return providers

    def get_resource_provider(self, uuid: str) -> ResourceProvider | None:
        """Get a resource provider by uuid."""
        with self._lock:
            return self._resource_providers.get(uuid)

    def get_resource_provider_by_name(self, name: str) -> ResourceProvider | None:
        """Get a resource provider by hypervisor hostname."""
        with self._lock:
            for provider in self._resource_providers.values():
                if provider.name == name:
                    return provider
            return None

    def get_resource_provider_inventories(self, uuid: str) -> dict[str, Any] | None:
        """Return the inventories document for a resource provider."""
        with self._lock:
            provider = self._resource_providers.get(uuid)
            if provider is None:
                return None
            return {
                "resource_provider_generation": provider.generation,
                "inventories": {
                    "VCPU": {
                        "total": provider.total_vcpus,
                        "reserved": provider.reserved_vcpus,
                        "min_unit": 1,
                        "max_unit": provider.total_vcpus,
                        "step_size": 1,
                        "allocation_ratio": provider.allocation_ratio_vcpu,
                    },
                    "MEMORY_MB": {
                        "total": provider.total_memory_mb,
                        "reserved": provider.reserved_memory_mb,
                        "min_unit": 1,
                        "max_unit": provider.total_memory_mb,
                        "step_size": 1,
                        "allocation_ratio": provider.allocation_ratio_memory,
                    },
                    "DISK_GB": {
                        "total": provider.total_disk_gb,
                        "reserved": provider.reserved_disk_gb,
                        "min_unit": 1,
                        "max_unit": provider.total_disk_gb,
                        "step_size": 1,
                        "allocation_ratio": provider.allocation_ratio_disk,
                    },
                },
            }

    def get_resource_provider_usages(self, uuid: str) -> dict[str, Any] | None:
        """Return the current usages document for a resource provider."""
        with self._lock:
            provider = self._resource_providers.get(uuid)
            if provider is None:
                return None
            usage = self._compute_compute_usage()
            return {
                "resource_provider_generation": provider.generation,
                "usages": {
                    "VCPU": usage["vcpus_used"],
                    "MEMORY_MB": usage["memory_mb_used"],
                    "DISK_GB": usage["disk_gb_used"],
                },
            }

    def get_allocation_candidates(
        self,
        resources: dict[str, int],
        required: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Placement ``/allocation_candidates``: which providers can place a request.

        Mirrors the real Placement pre-flight scheduler check. For each resource
        provider we compute effective capacity per resource class
        (``(total - reserved) * allocation_ratio``) minus current usage, and emit
        an allocation request only for providers that can currently fit every
        requested resource class and satisfy every required trait. Per the
        Placement API, ``required`` members may be forbidden traits (``!``-prefixed);
        emulator providers hold no traits, so a required trait excludes every
        provider while a forbidden trait is trivially satisfied.

        ``allocation_requests`` is empty when the cloud cannot currently place the
        request; callers (e.g. waldur-mastermind's WAL-9893 pre-flight order check)
        treat that as "no schedulable host". Only the requested resource classes
        are checked, so a VCPU/MEMORY_MB-only request never fails on DISK_GB.
        """
        # Providers carry no traits, so only positive required traits (not the
        # forbidden `!`-prefixed ones) can exclude a provider.
        has_required_trait = any(not trait.startswith("!") for trait in (required or []))
        allocation_requests: list[dict[str, Any]] = []
        provider_summaries: dict[str, Any] = {}
        with self._lock:
            usage = self._compute_compute_usage()
            used_by_class = {
                "VCPU": usage["vcpus_used"],
                "MEMORY_MB": usage["memory_mb_used"],
                "DISK_GB": usage["disk_gb_used"],
            }
            for provider in self._resource_providers.values():
                capacity = {
                    "VCPU": int(
                        (provider.total_vcpus - provider.reserved_vcpus)
                        * provider.allocation_ratio_vcpu
                    ),
                    "MEMORY_MB": int(
                        (provider.total_memory_mb - provider.reserved_memory_mb)
                        * provider.allocation_ratio_memory
                    ),
                    "DISK_GB": int(
                        (provider.total_disk_gb - provider.reserved_disk_gb)
                        * provider.allocation_ratio_disk
                    ),
                }
                # Emulator providers advertise no traits (see get_provider_traits).
                if has_required_trait:
                    continue
                fits = all(
                    rc in capacity and capacity[rc] - used_by_class.get(rc, 0) >= amount
                    for rc, amount in resources.items()
                )
                if not fits:
                    continue
                allocation_requests.append(
                    {
                        "allocations": {
                            provider.uuid: {"resources": dict(resources)},
                        }
                    }
                )
                provider_summaries[provider.uuid] = {
                    "resources": {
                        rc: {"capacity": cap, "used": used_by_class.get(rc, 0)}
                        for rc, cap in capacity.items()
                    },
                    "traits": [],
                    "generation": provider.generation,
                    "parent_provider_uuid": provider.parent_provider_uuid,
                    "root_provider_uuid": provider.root_provider_uuid or provider.uuid,
                }
        if limit is not None:
            allocation_requests = allocation_requests[:limit]
        return {
            "allocation_requests": allocation_requests,
            "provider_summaries": provider_summaries,
        }

    def _init_default_tokens(self) -> None:
        """Initialize tokens - currently empty, tokens should be created via authentication."""
        logger.info("Token initialization - no default tokens created")
        logger.info("Tokens will be created through proper authentication flow")

    def _init_nova_extensions(self) -> None:
        """Initialize Nova API extensions."""
        extensions = [
            NovaExtension(
                alias="os-volume_attachments",
                name="VolumeAttachments",
                namespace="http://docs.openstack.org/compute/ext/volume_attachments/api/v1.1",
                description="Volume attachment support.",
                updated="2011-06-09T00:00:00Z",
            ),
            NovaExtension(
                alias="os-interface",
                name="ServerNetworkInterfaces",
                namespace="http://docs.openstack.org/compute/ext/interfaces/api/v1.1",
                description="Server network interface support.",
                updated="2012-07-22T00:00:00Z",
            ),
            NovaExtension(
                alias="os-consoles",
                name="Consoles",
                namespace="http://docs.openstack.org/compute/ext/consoles/api/v2",
                description="Interactive Console support.",
                updated="2011-12-23T00:00:00Z",
            ),
            NovaExtension(
                alias="os-remote-consoles",
                name="RemoteConsoles",
                namespace="http://docs.openstack.org/compute/ext/remote_consoles/api/v1",
                description="Remote VNC console support.",
                updated="2014-12-04T00:00:00Z",
            ),
            NovaExtension(
                alias="os-server-diagnostics",
                name="ServerDiagnostics",
                namespace="http://docs.openstack.org/compute/ext/server-diagnostics/api/v1.1",
                description="Allow Admins to view server diagnostics through server action.",
                updated="2011-12-21T00:00:00Z",
            ),
            NovaExtension(
                alias="os-server-tags",
                name="ServerTags",
                namespace="http://docs.openstack.org/compute/ext/server_tags/api/v2",
                description="Server tags support.",
                updated="2016-01-19T00:00:00Z",
            ),
        ]

        for ext in extensions:
            self._nova_extensions[ext.alias] = ext

    # Nova Extensions API Methods

    def list_nova_extensions(self) -> list[NovaExtension]:
        """List all available Nova extensions."""
        with self._lock:
            return list(self._nova_extensions.values())

    def get_nova_extension(self, alias: str) -> NovaExtension | None:
        """Get a Nova extension by alias."""
        with self._lock:
            return self._nova_extensions.get(alias)

    # Server Volume Attachments

    def attach_volume_to_server(
        self,
        server_id: str,
        volume_id: str,
        device: str | None = None,
        tag: str | None = None,
        delete_on_termination: bool = False,
    ) -> ServerVolumeAttachment:
        """Attach a volume to a server."""
        with self._lock:
            if server_id not in self._server_volume_attachments:
                self._server_volume_attachments[server_id] = []

            attachment = ServerVolumeAttachment(
                volume_id=volume_id,
                server_id=server_id,
                device=device,
                tag=tag,
                delete_on_termination=delete_on_termination,
            )

            self._server_volume_attachments[server_id].append(attachment)
            return attachment

    def list_server_volume_attachments(self, server_id: str) -> list[ServerVolumeAttachment]:
        """List volume attachments for a server."""
        with self._lock:
            return self._server_volume_attachments.get(server_id, [])

    def get_server_volume_attachment(
        self, server_id: str, attachment_id: str
    ) -> ServerVolumeAttachment | None:
        """Get a specific volume attachment."""
        with self._lock:
            attachments = self._server_volume_attachments.get(server_id, [])
            return next((a for a in attachments if a.attachment_id == attachment_id), None)

    def detach_volume_from_server(self, server_id: str, attachment_id: str) -> bool:
        """Detach a volume from a server."""
        with self._lock:
            attachments = self._server_volume_attachments.get(server_id, [])
            for i, attachment in enumerate(attachments):
                if attachment.attachment_id == attachment_id:
                    del attachments[i]
                    return True
            return False

    # Server Network Interfaces

    def attach_interface_to_server(
        self,
        server_id: str,
        port: Port,
        nova_created: bool = False,
        availability_zone: str = "nova",
    ) -> ServerNetworkInterface:
        """Attach an existing Neutron port to a server.

        Mirrors Nova: the interface is backed by a real port, whose
        ``device_id``/``device_owner`` are set on attach. Port lookup and
        project-visibility belong to the API layer; the in-use check is
        enforced here, under the lock. ``nova_created`` marks ports created
        by Nova for this attach — they are deleted on detach/server delete
        instead of unbound.

        Raises:
            PortInUseError: If the port is already bound to a device.
        """
        with self._lock:
            if port.device_id:
                raise PortInUseError(port.id)

            if server_id not in self._server_network_interfaces:
                self._server_network_interfaces[server_id] = []

            port.device_id = server_id
            # Nova stamps the zone, not a fixed string:
            # port_req_body = {'port': {'device_id': instance.uuid,
            #                           'device_owner': 'compute:%s' % zone}}
            port.device_owner = f"compute:{availability_zone}"
            port.updated_at = datetime.utcnow()

            interface = ServerNetworkInterface(
                port_id=port.id,
                net_id=port.network_id,
                mac_addr=port.mac_address,
                fixed_ips=[ip.to_dict() for ip in port.fixed_ips],
                nova_created=nova_created,
            )

            self._server_network_interfaces[server_id].append(interface)
            if self.auto_save:
                self.save()
            return interface

    def list_server_network_interfaces(self, server_id: str) -> list[ServerNetworkInterface]:
        """List network interfaces for a server."""
        with self._lock:
            return self._server_network_interfaces.get(server_id, [])

    def get_server_network_interface(
        self, server_id: str, port_id: str
    ) -> ServerNetworkInterface | None:
        """Get a specific network interface."""
        with self._lock:
            interfaces = self._server_network_interfaces.get(server_id, [])
            return next((i for i in interfaces if i.port_id == port_id), None)

    def detach_interface_from_server(self, server_id: str, port_id: str) -> bool:
        """Detach a network interface from a server.

        Matches Nova's deallocate_port_for_instance: a port Nova created for
        the attach is deleted, a pre-existing port is unbound
        (``device_id``/``device_owner`` cleared).
        """
        with self._lock:
            interfaces = self._server_network_interfaces.get(server_id, [])
            for i, interface in enumerate(interfaces):
                if interface.port_id == port_id:
                    del interfaces[i]
                    self._release_interface_port(interface, server_id)
                    if self.auto_save:
                        self.save()
                    return True
            return False

    def _release_interface_port(self, interface: ServerNetworkInterface, server_id: str) -> None:
        """Delete a Nova-created backing port, or unbind a pre-existing one."""
        if interface.nova_created:
            self._ports.pop(interface.port_id, None)
            return
        port = self._ports.get(interface.port_id)
        if port and port.device_id == server_id:
            port.device_id = ""
            port.device_owner = ""
            port.updated_at = datetime.utcnow()

    # Server Console Support

    def create_server_console(self, server_id: str, console_type: str = "novnc") -> ServerConsole:
        """Create a console for a server."""
        with self._lock:
            if server_id not in self._server_consoles:
                self._server_consoles[server_id] = []

            console = ServerConsole(
                console_type=console_type,
                url=f"http://console.example.com:6080/vnc_auto.html?token={str(uuid4())}",
            )

            self._server_consoles[server_id].append(console)
            return console

    def list_server_consoles(self, server_id: str) -> list[ServerConsole]:
        """List consoles for a server."""
        with self._lock:
            return self._server_consoles.get(server_id, [])

    def get_server_console(self, server_id: str, console_id: str) -> ServerConsole | None:
        """Get a specific console."""
        with self._lock:
            consoles = self._server_consoles.get(server_id, [])
            return next((c for c in consoles if c.id == console_id), None)

    def delete_server_console(self, server_id: str, console_id: str) -> bool:
        """Delete a server console."""
        with self._lock:
            consoles = self._server_consoles.get(server_id, [])
            for i, console in enumerate(consoles):
                if console.id == console_id:
                    del consoles[i]
                    return True
            return False

    def create_remote_console(
        self, server_id: str, console_type: str = "novnc", protocol: str = "vnc"
    ) -> RemoteConsole:
        """Create a remote console for server access."""
        with self._lock:
            console = RemoteConsole(
                type=console_type,
                protocol=protocol,
                url=f"http://console.example.com:6080/vnc_auto.html?token={str(uuid4())}",
            )
            return console

    # Server Diagnostics

    def get_server_diagnostics(self, server_id: str) -> ServerDiagnostics:
        """Get server diagnostics information."""
        with self._lock:
            server = self._servers.get(server_id)
            if not server:
                raise ValueError(f"Server {server_id} not found")

            flavor = self._flavors.get(server.flavor_id)

            # Generate realistic diagnostics
            import random

            uptime = random.randint(3600, 86400 * 30)  # 1 hour to 30 days

            diagnostics = ServerDiagnostics(
                server_id=server_id,
                uptime=uptime,
                num_cpus=flavor.vcpus if flavor else 1,
                memory=flavor.ram if flavor else 512,
                cpu_details=[
                    {
                        "id": i,
                        "time": random.randint(100, 1000),
                        "utilization": f"{random.randint(10, 90)}%",
                    }
                    for i in range(flavor.vcpus if flavor else 1)
                ],
                nic_details=[
                    {
                        "mac_address": "fa:16:3e:xx:xx:xx",
                        "rx_bytes": random.randint(1000000, 10000000),
                        "tx_bytes": random.randint(1000000, 10000000),
                    }
                ],
                disk_details=[
                    {
                        "device": "/dev/vda",
                        "read_bytes": random.randint(1000000, 100000000),
                        "write_bytes": random.randint(1000000, 100000000),
                    }
                ],
            )
            return diagnostics

    # Server Tags

    def add_server_tag(self, server_id: str, tag: str) -> bool:
        """Add a tag to a server."""
        with self._lock:
            if server_id not in self._server_tags:
                self._server_tags[server_id] = set()
            self._server_tags[server_id].add(tag)
            return True

    def remove_server_tag(self, server_id: str, tag: str) -> bool:
        """Remove a tag from a server."""
        with self._lock:
            if server_id in self._server_tags and tag in self._server_tags[server_id]:
                self._server_tags[server_id].remove(tag)
                return True
            return False

    def list_server_tags(self, server_id: str) -> list[str]:
        """List tags for a server."""
        with self._lock:
            return list(self._server_tags.get(server_id, set()))

    def replace_server_tags(self, server_id: str, tags: list[str]) -> bool:
        """Replace all tags for a server."""
        with self._lock:
            self._server_tags[server_id] = set(tags)
            return True

    def clear_server_tags(self, server_id: str) -> bool:
        """Clear all tags for a server."""
        with self._lock:
            if server_id in self._server_tags:
                del self._server_tags[server_id]
                return True
            return False

    def _init_neutron_extensions(self) -> None:
        """Initialize Neutron API extensions."""
        extensions = [
            # Existing core extensions
            NeutronExtension(
                alias="security-group",
                name="security-group",
                namespace="http://docs.openstack.org/ext/neutron/security-group/api/v1.0",
                description="Security group support",
                updated="2023-01-01T00:00:00-00:00",
            ),
            NeutronExtension(
                alias="router",
                name="router",
                namespace="http://docs.openstack.org/ext/neutron/router/api/v1.0",
                description="Router support",
                updated="2023-01-01T00:00:00-00:00",
            ),
            NeutronExtension(
                alias="external-net",
                name="external-net",
                namespace="http://docs.openstack.org/ext/neutron/external-net/api/v1.0",
                description="External network support",
                updated="2023-01-01T00:00:00-00:00",
            ),
            NeutronExtension(
                alias="quotas",
                name="quotas",
                namespace="http://docs.openstack.org/ext/neutron/quotas/api/v1.0",
                description="Quota management support",
                updated="2023-01-01T00:00:00-00:00",
            ),
            NeutronExtension(
                alias="rbac-policies",
                name="rbac-policies",
                namespace="http://docs.openstack.org/ext/neutron/rbac-policies/api/v1.0",
                description="RBAC policy support for sharing resources",
                updated="2023-01-01T00:00:00-00:00",
            ),
            # New extensions
            NeutronExtension(
                alias="qos",
                name="Quality of Service",
                namespace="http://docs.openstack.org/ext/neutron/qos/api/v1.0",
                description="The Quality of Service extension.",
                updated="2015-06-08T10:00:00-00:00",
            ),
            NeutronExtension(
                alias="agent",
                name="agent",
                namespace="http://docs.openstack.org/ext/neutron/agent/api/v1.0",
                description="The agent management extension.",
                updated="2013-02-03T10:00:00-00:00",
            ),
            NeutronExtension(
                alias="trunk",
                name="Trunk Extension",
                namespace="http://docs.openstack.org/neutron/ext/trunk/api/v1.0",
                description="The trunk extension.",
                updated="2016-01-01T10:00:00-00:00",
            ),
            NeutronExtension(
                alias="trunk-details",
                name="Trunk port details",
                namespace="http://docs.openstack.org/neutron/ext/trunk-details/api/v1.0",
                description="The trunk port details extension.",
                updated="2016-01-01T10:00:00-00:00",
            ),
        ]

        # Initialize default QoS rule types
        rule_types = [
            QosRuleType(
                type="bandwidth_limit",
                drivers=[
                    {
                        "name": "ovs",
                        "supported_parameters": [
                            {
                                "parameter_name": "max_kbps",
                                "parameter_type": "range",
                                "parameter_range": {"min": 1},
                            },
                            {
                                "parameter_name": "max_burst_kbps",
                                "parameter_type": "range",
                                "parameter_range": {"min": 1},
                            },
                            {
                                "parameter_name": "direction",
                                "parameter_type": "choices",
                                "parameter_values": ["egress", "ingress"],
                            },
                        ],
                    }
                ],
            ),
            QosRuleType(
                type="dscp_marking",
                drivers=[
                    {
                        "name": "ovs",
                        "supported_parameters": [
                            {
                                "parameter_name": "dscp_mark",
                                "parameter_type": "choices",
                                "parameter_values": [
                                    0,
                                    8,
                                    10,
                                    12,
                                    14,
                                    16,
                                    18,
                                    20,
                                    22,
                                    24,
                                    26,
                                    28,
                                    30,
                                    32,
                                    34,
                                    36,
                                    38,
                                    40,
                                    46,
                                    48,
                                    56,
                                ],
                            }
                        ],
                    }
                ],
            ),
            QosRuleType(
                type="minimum_bandwidth",
                drivers=[
                    {
                        "name": "ovs",
                        "supported_parameters": [
                            {
                                "parameter_name": "min_kbps",
                                "parameter_type": "range",
                                "parameter_range": {"min": 1},
                            },
                            {
                                "parameter_name": "direction",
                                "parameter_type": "choices",
                                "parameter_values": ["egress", "ingress"],
                            },
                        ],
                    }
                ],
            ),
        ]

        # Initialize default agents
        agents = [
            NeutronAgent(
                agent_type="Open vSwitch agent",
                binary="neutron-openvswitch-agent",
                host="neutron-ovs-1",
                topic="N/A",
                configurations={
                    "ovs_hybrid_plug": False,
                    "bridge_mappings": {},
                    "tunneling_ip": "192.168.1.10",
                    "tunnel_types": ["vxlan", "gre"],
                    "l2_population": True,
                },
            ),
            NeutronAgent(
                agent_type="DHCP agent",
                binary="neutron-dhcp-agent",
                host="neutron-dhcp-1",
                topic="dhcp_agent",
                configurations={
                    "dhcp_driver": "neutron.agent.linux.dhcp.Dnsmasq",
                    "dhcp_lease_duration": 86400,
                    "networks": 0,
                    "ports": 0,
                    "subnets": 0,
                },
            ),
            NeutronAgent(
                agent_type="L3 agent",
                binary="neutron-l3-agent",
                host="neutron-l3-1",
                topic="l3_agent",
                configurations={
                    "agent_mode": "legacy",
                    "external_network_bridge": "br-ex",
                    "gateway_external_network_id": "",
                    "routers": 0,
                    "ex_gw_ports": 0,
                    "floating_ips": 0,
                },
            ),
            NeutronAgent(
                agent_type="Metadata agent",
                binary="neutron-metadata-agent",
                host="neutron-metadata-1",
                topic="N/A",
                configurations={
                    "metadata_proxy_socket": "/opt/stack/data/neutron/metadata_proxy",
                    "nova_metadata_host": "127.0.0.1",
                    "nova_metadata_port": 8775,
                },
            ),
        ]

        for ext in extensions:
            self._neutron_extensions[ext.alias] = ext

        for rule_type in rule_types:
            self._qos_rule_types[rule_type.type] = rule_type

        for agent in agents:
            self._neutron_agents[agent.id] = agent

        # Initialize default service profiles
        service_profiles = [
            ServiceProfile(
                description="Default L3 router service profile",
                driver="neutron.services.l3_router.drivers.default.DefaultDriver",
                enabled=True,
                metainfo='{"router_type": "legacy"}',
            ),
            ServiceProfile(
                description="High availability L3 router service profile",
                driver="neutron.services.l3_router.drivers.ha.HADriver",
                enabled=True,
                metainfo='{"router_type": "ha"}',
            ),
            ServiceProfile(
                description="Load balancer service profile",
                driver="neutron_lbaas.drivers.octavia.driver.OctaviaDriver",
                enabled=True,
                metainfo='{"lb_provider": "octavia"}',
            ),
        ]

        # Initialize default flavors
        neutron_flavors = [
            NeutronFlavor(
                name="default-router",
                description="Default L3 router flavor",
                service_type="L3_ROUTER_NAT",
                enabled=True,
                service_profiles=[service_profiles[0].id],
            ),
            NeutronFlavor(
                name="ha-router",
                description="High availability L3 router flavor",
                service_type="L3_ROUTER_NAT",
                enabled=True,
                service_profiles=[service_profiles[1].id],
            ),
            NeutronFlavor(
                name="default-loadbalancer",
                description="Default load balancer flavor",
                service_type="LOADBALANCERV2",
                enabled=True,
                service_profiles=[service_profiles[2].id],
            ),
        ]

        for profile in service_profiles:
            self._service_profiles[profile.id] = profile

        for flavor in neutron_flavors:
            self._neutron_flavors[flavor.id] = flavor

    # Neutron Extensions API Methods

    def list_neutron_extensions(self) -> list[NeutronExtension]:
        """List all available Neutron extensions."""
        with self._lock:
            return list(self._neutron_extensions.values())

    def get_neutron_extension(self, alias: str) -> NeutronExtension | None:
        """Get a Neutron extension by alias."""
        with self._lock:
            return self._neutron_extensions.get(alias)

    # QoS Policies

    def create_qos_policy(
        self,
        name: str,
        description: str = "",
        shared: bool = False,
        project_id: str = "",
        is_default: bool = False,
    ) -> QosPolicy:
        """Create a QoS policy."""
        with self._lock:
            policy = QosPolicy(
                name=name,
                description=description,
                shared=shared,
                project_id=project_id,
                is_default=is_default,
            )
            self._qos_policies[policy.id] = policy
            return policy

    def get_qos_policy(self, policy_id: str, project_id: str | None = None) -> QosPolicy | None:
        """Get a QoS policy by ID."""
        with self._lock:
            policy = self._qos_policies.get(policy_id)
            if policy is None:
                return None
            if project_id is not None and not policy.shared and policy.project_id != project_id:
                return None
            return policy

    def list_qos_policies(
        self,
        project_id: str | None = None,
        name: str | None = None,
        shared: bool | None = None,
    ) -> list[QosPolicy]:
        """List QoS policies with optional filtering."""
        with self._lock:
            policies = list(self._qos_policies.values())

            if project_id:
                policies = [p for p in policies if p.project_id == project_id or p.shared]
            if name:
                policies = [p for p in policies if p.name == name]
            if shared is not None:
                policies = [p for p in policies if p.shared == shared]

            return policies

    def update_qos_policy(
        self,
        policy_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        shared: bool | None = None,
    ) -> QosPolicy | None:
        """Update a QoS policy."""
        with self._lock:
            policy = self._qos_policies.get(policy_id)
            if not policy:
                return None
            if project_id is not None and policy.project_id != project_id:
                return None

            if name is not None:
                policy.name = name
            if description is not None:
                policy.description = description
            if shared is not None:
                policy.shared = shared
            policy.updated_at = datetime.now(timezone.utc)
            return policy

    def delete_qos_policy(self, policy_id: str, project_id: str | None = None) -> bool:
        """Delete a QoS policy."""
        with self._lock:
            policy = self._qos_policies.get(policy_id)
            if not policy:
                return False
            if project_id is not None and policy.project_id != project_id:
                return False
            del self._qos_policies[policy_id]
            return True

    def list_qos_rule_types(self) -> list[QosRuleType]:
        """List available QoS rule types."""
        with self._lock:
            return list(self._qos_rule_types.values())

    # Neutron Agents

    def list_neutron_agents(
        self,
        agent_type: str | None = None,
        host: str | None = None,
        alive: bool | None = None,
    ) -> list[NeutronAgent]:
        """List Neutron agents with optional filtering."""
        with self._lock:
            agents = list(self._neutron_agents.values())

            if agent_type:
                agents = [a for a in agents if a.agent_type == agent_type]
            if host:
                agents = [a for a in agents if a.host == host]
            if alive is not None:
                agents = [a for a in agents if a.alive == alive]

            return agents

    def get_neutron_agent(self, agent_id: str) -> NeutronAgent | None:
        """Get a Neutron agent by ID."""
        with self._lock:
            return self._neutron_agents.get(agent_id)

    def update_neutron_agent(
        self,
        agent_id: str,
        admin_state_up: bool | None = None,
        description: str | None = None,
    ) -> NeutronAgent | None:
        """Update a Neutron agent."""
        with self._lock:
            agent = self._neutron_agents.get(agent_id)
            if not agent:
                return None

            if admin_state_up is not None:
                agent.admin_state_up = admin_state_up
            agent.heartbeat_timestamp = datetime.now(timezone.utc)
            return agent

    def delete_neutron_agent(self, agent_id: str) -> bool:
        """Delete a Neutron agent."""
        with self._lock:
            if agent_id in self._neutron_agents:
                del self._neutron_agents[agent_id]
                return True
            return False

    # Trunks

    def create_trunk(
        self,
        name: str,
        port_id: str,
        description: str = "",
        admin_state_up: bool = True,
        project_id: str = "",
        sub_ports: list[dict[str, Any]] | None = None,
    ) -> Trunk:
        """Create a trunk."""
        with self._lock:
            trunk_sub_ports = []
            if sub_ports:
                for sp in sub_ports:
                    trunk_sub_ports.append(
                        TrunkSubPort(
                            port_id=sp.get("port_id", ""),
                            segmentation_type=sp.get("segmentation_type", "vlan"),
                            segmentation_id=sp.get("segmentation_id"),
                        )
                    )

            trunk = Trunk(
                name=name,
                port_id=port_id,
                description=description,
                admin_state_up=admin_state_up,
                project_id=project_id,
                sub_ports=trunk_sub_ports,
            )
            self._trunks[trunk.id] = trunk
            return trunk

    def get_trunk(self, trunk_id: str, project_id: str | None = None) -> Trunk | None:
        """Get a trunk by ID."""
        with self._lock:
            trunk = self._trunks.get(trunk_id)
            if trunk is None:
                return None
            if project_id is not None and trunk.project_id != project_id:
                return None
            return trunk

    def list_trunks(
        self,
        project_id: str | None = None,
        name: str | None = None,
        port_id: str | None = None,
    ) -> list[Trunk]:
        """List trunks with optional filtering."""
        with self._lock:
            trunks = list(self._trunks.values())

            if project_id:
                trunks = [t for t in trunks if t.project_id == project_id]
            if name:
                trunks = [t for t in trunks if t.name == name]
            if port_id:
                trunks = [t for t in trunks if t.port_id == port_id]

            return trunks

    def update_trunk(
        self,
        trunk_id: str,
        project_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        admin_state_up: bool | None = None,
    ) -> Trunk | None:
        """Update a trunk."""
        with self._lock:
            trunk = self._trunks.get(trunk_id)
            if not trunk:
                return None
            if project_id is not None and trunk.project_id != project_id:
                return None

            if name is not None:
                trunk.name = name
            if description is not None:
                trunk.description = description
            if admin_state_up is not None:
                trunk.admin_state_up = admin_state_up
            trunk.updated_at = datetime.now(timezone.utc)
            return trunk

    def delete_trunk(self, trunk_id: str, project_id: str | None = None) -> bool:
        """Delete a trunk."""
        with self._lock:
            trunk = self._trunks.get(trunk_id)
            if not trunk:
                return False
            if project_id is not None and trunk.project_id != project_id:
                return False
            del self._trunks[trunk_id]
            return True

    def add_subports_to_trunk(
        self,
        trunk_id: str,
        sub_ports: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> Trunk | None:
        """Add sub-ports to a trunk."""
        with self._lock:
            trunk = self._trunks.get(trunk_id)
            if not trunk:
                return None
            if project_id is not None and trunk.project_id != project_id:
                return None

            for sp in sub_ports:
                trunk_sub_port = TrunkSubPort(
                    port_id=sp.get("port_id", ""),
                    segmentation_type=sp.get("segmentation_type", "vlan"),
                    segmentation_id=sp.get("segmentation_id"),
                )
                trunk.sub_ports.append(trunk_sub_port)

            trunk.updated_at = datetime.now(timezone.utc)
            return trunk

    def remove_subports_from_trunk(
        self,
        trunk_id: str,
        sub_ports: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> Trunk | None:
        """Remove sub-ports from a trunk."""
        with self._lock:
            trunk = self._trunks.get(trunk_id)
            if not trunk:
                return None
            if project_id is not None and trunk.project_id != project_id:
                return None

            port_ids_to_remove = {sp.get("port_id") for sp in sub_ports}
            trunk.sub_ports = [sp for sp in trunk.sub_ports if sp.port_id not in port_ids_to_remove]
            trunk.updated_at = datetime.now(timezone.utc)
            return trunk

    def _init_octavia_extensions(self) -> None:
        """Initialize Octavia extensions and default data."""
        # Initialize default providers
        providers = [
            LoadBalancerProvider(
                name="amphora",
                description="The Octavia Amphora driver",
            ),
            LoadBalancerProvider(
                name="ovn",
                description="The OVN Octavia provider driver",
            ),
        ]

        # Initialize default availability zones
        az_profiles = [
            LoadBalancerAvailabilityZoneProfile(
                name="nova-az1-profile",
                provider_name="amphora",
                availability_zone_data='{"compute_zone": "nova"}',
            ),
        ]

        availability_zones = [
            LoadBalancerAvailabilityZone(
                name="nova",
                description="Default availability zone",
                enabled=True,
                availability_zone_profile_id="nova-az1-profile",
            ),
        ]

        # Initialize default flavor profiles
        flavor_profiles = [
            LoadBalancerFlavorProfile(
                name="default-amphora-profile",
                provider_name="amphora",
                flavor_data='{"loadbalancer_topology": "SINGLE"}',
            ),
            LoadBalancerFlavorProfile(
                name="ha-amphora-profile",
                provider_name="amphora",
                flavor_data='{"loadbalancer_topology": "ACTIVE_STANDBY"}',
            ),
        ]

        # Initialize default flavors
        flavors = [
            LoadBalancerFlavor(
                name="default",
                description="Default load balancer flavor",
                enabled=True,
                flavor_profile_id="default-amphora-profile",
            ),
            LoadBalancerFlavor(
                name="ha",
                description="High availability load balancer flavor",
                enabled=True,
                flavor_profile_id="ha-amphora-profile",
            ),
        ]

        for provider in providers:
            self._lb_providers[provider.name] = provider

        for az_profile in az_profiles:
            self._lb_availability_zone_profiles[az_profile.id] = az_profile

        for az in availability_zones:
            self._lb_availability_zones[az.name] = az

        for flavor_profile in flavor_profiles:
            self._lb_flavor_profiles[flavor_profile.id] = flavor_profile

        for flavor in flavors:
            self._lb_flavors[flavor.id] = flavor

    # Octavia Extensions API Methods

    def get_octavia_quota(self, project_id: str) -> OctaviaQuota:
        """Get Octavia quota for a project."""
        with self._lock:
            quota = self._octavia_quotas.get(project_id)
            if not quota:
                quota = OctaviaQuota(project_id=project_id)
                self._octavia_quotas[project_id] = quota
            return quota

    def list_octavia_quotas(self) -> list[OctaviaQuota]:
        """List all Octavia quotas."""
        with self._lock:
            return list(self._octavia_quotas.values())

    def update_octavia_quota(self, project_id: str, **kwargs: Any) -> OctaviaQuota:
        """Update Octavia quota for a project."""
        with self._lock:
            quota = self.get_octavia_quota(project_id)
            for key, value in kwargs.items():
                if hasattr(quota, key) and value is not None:
                    setattr(quota, key, value)
            return quota

    def delete_octavia_quota(self, project_id: str) -> bool:
        """Reset Octavia quota to defaults for a project."""
        with self._lock:
            if project_id in self._octavia_quotas:
                del self._octavia_quotas[project_id]
                return True
            return False

    def get_octavia_quota_usage(self, project_id: str) -> dict[str, int]:
        """Calculate Octavia quota usage for a project."""
        with self._lock:
            loadbalancers = [
                lb for lb in self._load_balancers.values() if lb.project_id == project_id
            ]
            listeners = [
                listener
                for listener in self._listeners.values()
                if listener.project_id == project_id
            ]
            pools = [p for p in self._pools.values() if p.project_id == project_id]
            members = [m for m in self._pool_members.values() if m.project_id == project_id]
            health_monitors = [
                h for h in self._health_monitors.values() if h.project_id == project_id
            ]
            l7policies = [p for p in self._l7policies.values() if p.project_id == project_id]
            l7rules = [r for r in self._l7rules.values() if r.project_id == project_id]

            return {
                "loadbalancer": len(loadbalancers),
                "listener": len(listeners),
                "pool": len(pools),
                "member": len(members),
                "healthmonitor": len(health_monitors),
                "l7policy": len(l7policies),
                "l7rule": len(l7rules),
            }

    def list_lb_providers(self) -> list[LoadBalancerProvider]:
        """List load balancer providers."""
        with self._lock:
            return list(self._lb_providers.values())

    def get_lb_provider(self, provider_name: str) -> LoadBalancerProvider | None:
        """Get a load balancer provider by name."""
        with self._lock:
            return self._lb_providers.get(provider_name)

    def list_lb_flavors(self) -> list[LoadBalancerFlavor]:
        """List load balancer flavors."""
        with self._lock:
            return list(self._lb_flavors.values())

    def get_lb_flavor(self, flavor_id: str) -> LoadBalancerFlavor | None:
        """Get a load balancer flavor by ID."""
        with self._lock:
            return self._lb_flavors.get(flavor_id)

    def list_lb_flavor_profiles(self) -> list[LoadBalancerFlavorProfile]:
        """List load balancer flavor profiles."""
        with self._lock:
            return list(self._lb_flavor_profiles.values())

    def get_lb_flavor_profile(self, profile_id: str) -> LoadBalancerFlavorProfile | None:
        """Get a load balancer flavor profile by ID."""
        with self._lock:
            return self._lb_flavor_profiles.get(profile_id)

    def list_lb_availability_zones(self) -> list[LoadBalancerAvailabilityZone]:
        """List load balancer availability zones."""
        with self._lock:
            return list(self._lb_availability_zones.values())

    def get_lb_availability_zone(self, az_name: str) -> LoadBalancerAvailabilityZone | None:
        """Get a load balancer availability zone by name."""
        with self._lock:
            return self._lb_availability_zones.get(az_name)

    def list_lb_availability_zone_profiles(self) -> list[LoadBalancerAvailabilityZoneProfile]:
        """List load balancer availability zone profiles."""
        with self._lock:
            return list(self._lb_availability_zone_profiles.values())

    def get_lb_availability_zone_profile(
        self, profile_id: str
    ) -> LoadBalancerAvailabilityZoneProfile | None:
        """Get a load balancer availability zone profile by ID."""
        with self._lock:
            return self._lb_availability_zone_profiles.get(profile_id)

    # Cinder Extensions API Methods

    # Volume Transfers

    def create_volume_transfer(
        self,
        name: str,
        volume_id: str,
        project_id: str,
    ) -> VolumeTransfer:
        """Create a volume transfer."""
        with self._lock:
            # Verify volume exists and belongs to project
            volume = self.get_volume(volume_id, project_id=project_id)
            if not volume:
                raise ValueError("Volume not found or access denied")

            transfer = VolumeTransfer(
                name=name,
                volume_id=volume_id,
                source_project_id=project_id,
            )
            self._volume_transfers[transfer.id] = transfer
            return transfer

    def list_volume_transfers(
        self,
        project_id: str | None = None,
        all_tenants: bool = False,
    ) -> list[VolumeTransfer]:
        """List volume transfers."""
        with self._lock:
            transfers = list(self._volume_transfers.values())
            if project_id and not all_tenants:
                transfers = [t for t in transfers if t.source_project_id == project_id]
            return transfers

    def get_volume_transfer(
        self, transfer_id: str, project_id: str | None = None
    ) -> VolumeTransfer | None:
        """Get a volume transfer by ID."""
        with self._lock:
            transfer = self._volume_transfers.get(transfer_id)
            if not transfer:
                return None
            if project_id and transfer.source_project_id != project_id:
                return None
            return transfer

    def accept_volume_transfer(
        self,
        transfer_id: str,
        auth_key: str,
        destination_project_id: str,
    ) -> VolumeTransfer | None:
        """Accept a volume transfer."""
        with self._lock:
            transfer = self._volume_transfers.get(transfer_id)
            if not transfer or transfer.auth_key != auth_key:
                return None

            # Move volume to destination project
            volume = self._volumes.get(transfer.volume_id)
            if volume:
                volume.project_id = destination_project_id

            transfer.destination_project_id = destination_project_id
            transfer.accepted = True
            return transfer

    def delete_volume_transfer(self, transfer_id: str, project_id: str | None = None) -> bool:
        """Delete a volume transfer."""
        with self._lock:
            transfer = self._volume_transfers.get(transfer_id)
            if not transfer:
                return False
            if project_id and transfer.source_project_id != project_id:
                return False
            del self._volume_transfers[transfer_id]
            return True

    # Volume Backups

    def create_volume_backup(
        self,
        name: str,
        volume_id: str,
        description: str = "",
        container: str = "volumebackups",
        incremental: bool = False,
        snapshot_id: str | None = None,
        project_id: str = "",
        user_id: str = "",
    ) -> VolumeBackup:
        """Create a volume backup."""
        with self._lock:
            # Get volume to inherit size
            volume = self.get_volume(volume_id, project_id=project_id)
            if not volume:
                raise ValueError("Volume not found")

            backup = VolumeBackup(
                name=name,
                description=description,
                volume_id=volume_id,
                container=container,
                size=volume.size,
                project_id=project_id,
                user_id=user_id,
                is_incremental=incremental,
                snapshot_id=snapshot_id,
            )
            # Simulate immediate availability
            backup.status = BackupStatus.AVAILABLE
            self._volume_backups[backup.id] = backup
            return backup

    def list_volume_backups(
        self,
        project_id: str | None = None,
        volume_id: str | None = None,
        all_tenants: bool = False,
    ) -> list[VolumeBackup]:
        """List volume backups."""
        with self._lock:
            backups = list(self._volume_backups.values())
            if project_id and not all_tenants:
                backups = [b for b in backups if b.project_id == project_id]
            if volume_id:
                backups = [b for b in backups if b.volume_id == volume_id]
            return backups

    def get_volume_backup(
        self, backup_id: str, project_id: str | None = None
    ) -> VolumeBackup | None:
        """Get a volume backup by ID."""
        with self._lock:
            backup = self._volume_backups.get(backup_id)
            if not backup:
                return None
            if project_id and backup.project_id != project_id:
                return None
            return backup

    def delete_volume_backup(self, backup_id: str, project_id: str | None = None) -> bool:
        """Delete a volume backup."""
        with self._lock:
            backup = self._volume_backups.get(backup_id)
            if not backup:
                return False
            if project_id and backup.project_id != project_id:
                return False
            del self._volume_backups[backup_id]
            return True

    def restore_volume_backup(
        self,
        backup_id: str,
        volume_id: str | None = None,
        name: str | None = None,
        project_id: str | None = None,
    ) -> Volume | None:
        """Restore a volume from backup."""
        with self._lock:
            backup = self.get_volume_backup(backup_id, project_id=project_id)
            if not backup:
                return None

            if volume_id:
                # Restore to existing volume
                volume = self.get_volume(volume_id, project_id=project_id)
                if not volume:
                    return None
                # In reality this would overwrite volume data
                return volume
            else:
                # Create new volume from backup
                volume_name = name or f"restore-{backup.name}"
                return self.create_volume(
                    name=volume_name,
                    size=backup.size,
                    project_id=backup.project_id,
                    user_id=backup.user_id,
                    availability_zone=backup.availability_zone,
                )

    # Consistency Groups

    def create_consistency_group(
        self,
        name: str,
        description: str = "",
        volume_types: list[str] | None = None,
        availability_zone: str = "nova",
        project_id: str = "",
        user_id: str = "",
    ) -> ConsistencyGroup:
        """Create a consistency group."""
        with self._lock:
            group = ConsistencyGroup(
                name=name,
                description=description,
                volume_types=volume_types or [],
                availability_zone=availability_zone,
                project_id=project_id,
                user_id=user_id,
            )
            # Simulate immediate availability
            group.status = GroupStatus.AVAILABLE
            self._consistency_groups[group.id] = group
            return group

    def list_consistency_groups(
        self,
        project_id: str | None = None,
        all_tenants: bool = False,
    ) -> list[ConsistencyGroup]:
        """List consistency groups."""
        with self._lock:
            groups = list(self._consistency_groups.values())
            if project_id and not all_tenants:
                groups = [g for g in groups if g.project_id == project_id]
            return groups

    def get_consistency_group(
        self, group_id: str, project_id: str | None = None
    ) -> ConsistencyGroup | None:
        """Get a consistency group by ID."""
        with self._lock:
            group = self._consistency_groups.get(group_id)
            if not group:
                return None
            if project_id and group.project_id != project_id:
                return None
            return group

    def delete_consistency_group(self, group_id: str, project_id: str | None = None) -> bool:
        """Delete a consistency group."""
        with self._lock:
            group = self._consistency_groups.get(group_id)
            if not group:
                return False
            if project_id and group.project_id != project_id:
                return False
            del self._consistency_groups[group_id]
            return True

    def create_group_snapshot(
        self,
        name: str,
        group_id: str,
        description: str = "",
        project_id: str = "",
        user_id: str = "",
    ) -> GroupSnapshot:
        """Create a group snapshot."""
        with self._lock:
            group = self.get_consistency_group(group_id, project_id=project_id)
            if not group:
                raise ValueError("Consistency group not found")

            snapshot = GroupSnapshot(
                name=name,
                description=description,
                group_id=group_id,
                group_type_id=group.group_type,
                project_id=project_id,
                user_id=user_id,
            )
            # Simulate immediate availability
            snapshot.status = GroupStatus.AVAILABLE
            self._group_snapshots[snapshot.id] = snapshot
            return snapshot

    def list_group_snapshots(
        self,
        project_id: str | None = None,
        group_id: str | None = None,
        all_tenants: bool = False,
    ) -> list[GroupSnapshot]:
        """List group snapshots."""
        with self._lock:
            snapshots = list(self._group_snapshots.values())
            if project_id and not all_tenants:
                snapshots = [s for s in snapshots if s.project_id == project_id]
            if group_id:
                snapshots = [s for s in snapshots if s.group_id == group_id]
            return snapshots

    def get_group_snapshot(
        self, snapshot_id: str, project_id: str | None = None
    ) -> GroupSnapshot | None:
        """Get a group snapshot by ID."""
        with self._lock:
            snapshot = self._group_snapshots.get(snapshot_id)
            if not snapshot:
                return None
            if project_id and snapshot.project_id != project_id:
                return None
            return snapshot

    def delete_group_snapshot(self, snapshot_id: str, project_id: str | None = None) -> bool:
        """Delete a group snapshot."""
        with self._lock:
            snapshot = self._group_snapshots.get(snapshot_id)
            if not snapshot:
                return False
            if project_id and snapshot.project_id != project_id:
                return False
            del self._group_snapshots[snapshot_id]
            return True

    def _init_glance_extensions(self) -> None:
        """Initialize Glance extensions and default data."""
        # Initialize default stores
        stores = [
            GlanceStore(
                id="default",
                type="file",
                description="Default file-based store",
                default=True,
            ),
            GlanceStore(
                id="swift",
                type="swift",
                description="Swift object storage",
                default=False,
            ),
        ]

        for store in stores:
            self._glance_stores[store.id] = store

    # Glance Extensions API Methods

    # Image Tasks

    def create_image_task(
        self,
        task_type: TaskType,
        input_data: dict[str, Any],
        owner: str = "",
    ) -> ImageTask:
        """Create an image task."""
        with self._lock:
            task = ImageTask(
                type=task_type,
                owner=owner,
                input=input_data,
            )
            # Simulate immediate success for testing
            task.status = TaskStatus.SUCCESS
            task.result = {"image_id": str(uuid4())} if task_type == TaskType.IMPORT else {}
            self._image_tasks[task.id] = task
            return task

    def list_image_tasks(
        self,
        owner: str | None = None,
        status: TaskStatus | None = None,
        type: TaskType | None = None,
    ) -> list[ImageTask]:
        """List image tasks."""
        with self._lock:
            tasks = list(self._image_tasks.values())
            if owner:
                tasks = [t for t in tasks if t.owner == owner]
            if status:
                tasks = [t for t in tasks if t.status == status]
            if type:
                tasks = [t for t in tasks if t.type == type]
            return tasks

    def get_image_task(self, task_id: str, owner: str | None = None) -> ImageTask | None:
        """Get an image task by ID."""
        with self._lock:
            task = self._image_tasks.get(task_id)
            if not task:
                return None
            if owner and task.owner != owner:
                return None
            return task

    def delete_image_task(self, task_id: str, owner: str | None = None) -> bool:
        """Delete an image task."""
        with self._lock:
            task = self._image_tasks.get(task_id)
            if not task:
                return False
            if owner and task.owner != owner:
                return False
            del self._image_tasks[task_id]
            return True

    # Metadata Definitions

    def create_metadef_namespace(
        self,
        namespace: str,
        display_name: str = "",
        description: str = "",
        visibility: str = "private",
        owner: str = "",
        properties: dict[str, Any] | None = None,
    ) -> MetadefNamespace:
        """Create a metadata definition namespace."""
        with self._lock:
            metadef = MetadefNamespace(
                namespace=namespace,
                display_name=display_name,
                description=description,
                visibility=visibility,
                owner=owner,
                properties=properties or {},
            )
            self._metadef_namespaces[namespace] = metadef
            return metadef

    def list_metadef_namespaces(
        self,
        owner: str | None = None,
        visibility: str | None = None,
    ) -> list[MetadefNamespace]:
        """List metadata definition namespaces."""
        with self._lock:
            namespaces = list(self._metadef_namespaces.values())
            if owner:
                namespaces = [n for n in namespaces if n.owner == owner or n.visibility == "public"]
            if visibility:
                namespaces = [n for n in namespaces if n.visibility == visibility]
            return namespaces

    def get_metadef_namespace(
        self, namespace: str, owner: str | None = None
    ) -> MetadefNamespace | None:
        """Get a metadata definition namespace."""
        with self._lock:
            metadef = self._metadef_namespaces.get(namespace)
            if not metadef:
                return None
            if owner and metadef.owner != owner and metadef.visibility != "public":
                return None
            return metadef

    def update_metadef_namespace(
        self, namespace: str, owner: str | None = None, **kwargs: Any
    ) -> MetadefNamespace | None:
        """Update a metadata definition namespace."""
        with self._lock:
            metadef = self._metadef_namespaces.get(namespace)
            if not metadef:
                return None
            if owner and metadef.owner != owner:
                return None

            for key, value in kwargs.items():
                if hasattr(metadef, key) and value is not None:
                    setattr(metadef, key, value)
            metadef.updated_at = datetime.now(timezone.utc)
            return metadef

    def delete_metadef_namespace(self, namespace: str, owner: str | None = None) -> bool:
        """Delete a metadata definition namespace."""
        with self._lock:
            metadef = self._metadef_namespaces.get(namespace)
            if not metadef:
                return False
            if owner and metadef.owner != owner:
                return False
            del self._metadef_namespaces[namespace]
            return True

    # Image Cache

    def get_image_cache_status(self) -> dict[str, Any]:
        """Get image cache status."""
        with self._lock:
            cached_images = list(self._image_cache.values())
            total_size = sum(entry.size for entry in cached_images)
            return {
                "cached_images": [entry.to_dict() for entry in cached_images],
                "queued_images": [],  # Simplified - no queue in this implementation
                "total_size": total_size,
                "cache_count": len(cached_images),
            }

    def cache_image(self, image_id: str, size: int = 0) -> ImageCacheEntry:
        """Add an image to cache."""
        with self._lock:
            entry = ImageCacheEntry(
                image_id=image_id,
                size=size,
                hits=0,
            )
            self._image_cache[image_id] = entry
            return entry

    def delete_cached_image(self, image_id: str) -> bool:
        """Remove an image from cache."""
        with self._lock:
            if image_id in self._image_cache:
                del self._image_cache[image_id]
                return True
            return False

    def clear_image_cache(self) -> bool:
        """Clear all cached images."""
        with self._lock:
            self._image_cache.clear()
            return True

    # Glance Stores

    def list_glance_stores(self) -> list[GlanceStore]:
        """List available Glance stores."""
        with self._lock:
            return list(self._glance_stores.values())

    def get_glance_store(self, store_id: str) -> GlanceStore | None:
        """Get a Glance store by ID."""
        with self._lock:
            return self._glance_stores.get(store_id)

    def _init_keystone_extensions(self) -> None:
        """Initialize Keystone extensions and default data."""
        # Initialize default registered limits
        limits = [
            RegisteredLimit(
                service_id="nova",
                resource_name="instances",
                default_limit=10,
                description="Default instance limit per project",
            ),
            RegisteredLimit(
                service_id="nova",
                resource_name="cores",
                default_limit=20,
                description="Default core limit per project",
            ),
            RegisteredLimit(
                service_id="cinder",
                resource_name="volumes",
                default_limit=10,
                description="Default volume limit per project",
            ),
            RegisteredLimit(
                service_id="neutron",
                resource_name="networks",
                default_limit=100,
                description="Default network limit per project",
            ),
        ]

        for limit in limits:
            self._registered_limits[limit.id] = limit

    # Keystone Extensions API Methods

    # Application Credentials

    def create_application_credential(
        self,
        user_id: str,
        name: str,
        description: str = "",
        project_id: str | None = None,
        expires_at: datetime | None = None,
        roles: list[dict[str, str]] | None = None,
        unrestricted: bool = False,
    ) -> ApplicationCredential:
        """Create an application credential."""
        with self._lock:
            cred = ApplicationCredential(
                name=name,
                description=description,
                user_id=user_id,
                project_id=project_id,
                expires_at=expires_at,
                roles=roles or [],
                unrestricted=unrestricted,
            )
            key = f"{user_id}:{cred.id}"
            self._application_credentials[key] = cred
            return cred

    def list_application_credentials(self, user_id: str) -> list[ApplicationCredential]:
        """List application credentials for a user."""
        with self._lock:
            return [
                cred
                for key, cred in self._application_credentials.items()
                if key.startswith(f"{user_id}:")
            ]

    def get_application_credential(
        self, user_id: str, cred_id: str
    ) -> ApplicationCredential | None:
        """Get an application credential."""
        with self._lock:
            key = f"{user_id}:{cred_id}"
            return self._application_credentials.get(key)

    def find_application_credential(
        self, cred_id: str | None = None, name: str | None = None, user_id: str | None = None
    ) -> ApplicationCredential | None:
        """Find an application credential by id, or by name within a user.

        Authentication addresses a credential by id alone (the id is globally
        unique) or by name plus the owning user, so neither lookup can go
        through :meth:`get_application_credential`, which needs both parts of
        the storage key.
        """
        with self._lock:
            for cred in self._application_credentials.values():
                if cred_id is not None and cred.id != cred_id:
                    continue
                if name is not None and cred.name != name:
                    continue
                if user_id is not None and cred.user_id != user_id:
                    continue
                return cred
            return None

    def delete_application_credential(self, user_id: str, cred_id: str) -> bool:
        """Delete an application credential."""
        with self._lock:
            key = f"{user_id}:{cred_id}"
            if key in self._application_credentials:
                del self._application_credentials[key]
                return True
            return False

    # Policy Management

    def create_policy(
        self,
        blob: str,
        type: str = "application/json",
        user_id: str = "",
        project_id: str | None = None,
    ) -> PolicyDocument:
        """Create a policy document."""
        with self._lock:
            policy = PolicyDocument(
                blob=blob,
                type=type,
                user_id=user_id,
                project_id=project_id,
            )
            self._policy_documents[policy.id] = policy
            return policy

    def list_policies(self) -> list[PolicyDocument]:
        """List policy documents."""
        with self._lock:
            return list(self._policy_documents.values())

    def get_policy(self, policy_id: str) -> PolicyDocument | None:
        """Get a policy document by ID."""
        with self._lock:
            return self._policy_documents.get(policy_id)

    def update_policy(
        self,
        policy_id: str,
        blob: str | None = None,
        type: str | None = None,
    ) -> PolicyDocument | None:
        """Update a policy document."""
        with self._lock:
            policy = self._policy_documents.get(policy_id)
            if not policy:
                return None
            if blob is not None:
                policy.blob = blob
            if type is not None:
                policy.type = type
            policy.updated_at = datetime.now(timezone.utc)
            return policy

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy document."""
        with self._lock:
            if policy_id in self._policy_documents:
                del self._policy_documents[policy_id]
                return True
            return False

    # Federation

    def create_identity_provider(
        self,
        idp_id: str,
        description: str = "",
        enabled: bool = True,
        remote_ids: list[str] | None = None,
        domain_id: str = "default",
    ) -> IdentityProvider:
        """Create an identity provider."""
        with self._lock:
            idp = IdentityProvider(
                id=idp_id,
                description=description,
                enabled=enabled,
                remote_ids=remote_ids or [],
                domain_id=domain_id,
            )
            self._identity_providers[idp_id] = idp
            return idp

    def list_identity_providers(self) -> list[IdentityProvider]:
        """List identity providers."""
        with self._lock:
            return list(self._identity_providers.values())

    def get_identity_provider(self, idp_id: str) -> IdentityProvider | None:
        """Get an identity provider by ID."""
        with self._lock:
            return self._identity_providers.get(idp_id)

    def update_identity_provider(
        self,
        idp_id: str,
        description: str | None = None,
        enabled: bool | None = None,
        remote_ids: list[str] | None = None,
    ) -> IdentityProvider | None:
        """Update an identity provider."""
        with self._lock:
            idp = self._identity_providers.get(idp_id)
            if not idp:
                return None
            if description is not None:
                idp.description = description
            if enabled is not None:
                idp.enabled = enabled
            if remote_ids is not None:
                idp.remote_ids = remote_ids
            return idp

    def delete_identity_provider(self, idp_id: str) -> bool:
        """Delete an identity provider."""
        with self._lock:
            if idp_id in self._identity_providers:
                del self._identity_providers[idp_id]
                return True
            return False

    def create_federation_protocol(
        self,
        idp_id: str,
        protocol_id: str,
        mapping_id: str,
    ) -> FederationProtocol:
        """Create a federation protocol."""
        with self._lock:
            protocol = FederationProtocol(
                id=protocol_id,
                mapping_id=mapping_id,
                identity_provider_id=idp_id,
            )
            key = f"{idp_id}:{protocol_id}"
            self._federation_protocols[key] = protocol
            return protocol

    def list_federation_protocols(self, idp_id: str) -> list[FederationProtocol]:
        """List federation protocols for an identity provider."""
        with self._lock:
            return [
                protocol
                for key, protocol in self._federation_protocols.items()
                if key.startswith(f"{idp_id}:")
            ]

    def get_federation_protocol(self, idp_id: str, protocol_id: str) -> FederationProtocol | None:
        """Get a federation protocol."""
        with self._lock:
            key = f"{idp_id}:{protocol_id}"
            return self._federation_protocols.get(key)

    def delete_federation_protocol(self, idp_id: str, protocol_id: str) -> bool:
        """Delete a federation protocol."""
        with self._lock:
            key = f"{idp_id}:{protocol_id}"
            if key in self._federation_protocols:
                del self._federation_protocols[key]
                return True
            return False

    def create_service_provider(
        self,
        sp_id: str,
        auth_url: str = "",
        sp_url: str = "",
        description: str = "",
        enabled: bool = True,
        relay_state_prefix: str = "ss:mem:",
    ) -> ServiceProvider:
        """Register a service provider."""
        with self._lock:
            provider = ServiceProvider(
                id=sp_id,
                auth_url=auth_url,
                sp_url=sp_url,
                description=description,
                enabled=enabled,
                relay_state_prefix=relay_state_prefix,
            )
            self._service_providers[sp_id] = provider
            if self.auto_save:
                self.save()
            return provider

    def list_service_providers(self) -> list[ServiceProvider]:
        """List registered service providers."""
        with self._lock:
            return list(self._service_providers.values())

    def get_service_provider(self, sp_id: str) -> ServiceProvider | None:
        """Get a registered service provider."""
        with self._lock:
            return self._service_providers.get(sp_id)

    def delete_service_provider(self, sp_id: str) -> bool:
        """Remove a registered service provider."""
        with self._lock:
            if sp_id in self._service_providers:
                del self._service_providers[sp_id]
                if self.auto_save:
                    self.save()
                return True
            return False

    def create_federation_mapping(
        self,
        mapping_id: str,
        rules: list[dict[str, Any]],
    ) -> FederationMapping:
        """Create a federation mapping."""
        with self._lock:
            mapping = FederationMapping(
                id=mapping_id,
                rules=rules,
            )
            self._federation_mappings[mapping_id] = mapping
            return mapping

    def list_federation_mappings(self) -> list[FederationMapping]:
        """List federation mappings."""
        with self._lock:
            return list(self._federation_mappings.values())

    def get_federation_mapping(self, mapping_id: str) -> FederationMapping | None:
        """Get a federation mapping by ID."""
        with self._lock:
            return self._federation_mappings.get(mapping_id)

    def update_federation_mapping(
        self,
        mapping_id: str,
        rules: list[dict[str, Any]],
    ) -> FederationMapping | None:
        """Update a federation mapping."""
        with self._lock:
            mapping = self._federation_mappings.get(mapping_id)
            if not mapping:
                return None
            mapping.rules = rules
            return mapping

    def delete_federation_mapping(self, mapping_id: str) -> bool:
        """Delete a federation mapping."""
        with self._lock:
            if mapping_id in self._federation_mappings:
                del self._federation_mappings[mapping_id]
                return True
            return False

    # Registered Limits

    def list_registered_limits(
        self,
        service_id: str | None = None,
        resource_name: str | None = None,
    ) -> list[RegisteredLimit]:
        """List registered limits."""
        with self._lock:
            limits = list(self._registered_limits.values())
            if service_id:
                limits = [limit for limit in limits if limit.service_id == service_id]
            if resource_name:
                limits = [limit for limit in limits if limit.resource_name == resource_name]
            return limits

    def get_registered_limit(self, limit_id: str) -> RegisteredLimit | None:
        """Get a registered limit by ID."""
        with self._lock:
            return self._registered_limits.get(limit_id)

    def create_registered_limit(
        self,
        service_id: str,
        resource_name: str,
        default_limit: int,
        description: str = "",
        region_id: str | None = None,
    ) -> RegisteredLimit:
        """Create a registered limit."""
        with self._lock:
            limit = RegisteredLimit(
                service_id=service_id,
                resource_name=resource_name,
                default_limit=default_limit,
                description=description,
                region_id=region_id,
            )
            self._registered_limits[limit.id] = limit
            return limit

    def update_registered_limit(
        self,
        limit_id: str,
        default_limit: int | None = None,
        description: str | None = None,
    ) -> RegisteredLimit | None:
        """Update a registered limit."""
        with self._lock:
            limit = self._registered_limits.get(limit_id)
            if not limit:
                return None
            if default_limit is not None:
                limit.default_limit = default_limit
            if description is not None:
                limit.description = description
            return limit

    def delete_registered_limit(self, limit_id: str) -> bool:
        """Delete a registered limit."""
        with self._lock:
            if limit_id in self._registered_limits:
                del self._registered_limits[limit_id]
                return True
            return False

    # Neutron Flavors

    def list_neutron_flavors(
        self,
        service_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[NeutronFlavor]:
        """List Neutron service flavors."""
        with self._lock:
            flavors = list(self._neutron_flavors.values())
            if service_type:
                flavors = [f for f in flavors if f.service_type == service_type]
            if enabled is not None:
                flavors = [f for f in flavors if f.enabled == enabled]
            return flavors

    def get_neutron_flavor(self, flavor_id: str) -> NeutronFlavor | None:
        """Get a Neutron service flavor by ID."""
        with self._lock:
            return self._neutron_flavors.get(flavor_id)

    def create_neutron_flavor(
        self,
        name: str,
        description: str = "",
        service_type: str = "",
        enabled: bool = True,
        service_profiles: list[str] | None = None,
    ) -> NeutronFlavor:
        """Create a Neutron service flavor."""
        with self._lock:
            flavor = NeutronFlavor(
                name=name,
                description=description,
                service_type=service_type,
                enabled=enabled,
                service_profiles=service_profiles or [],
            )
            self._neutron_flavors[flavor.id] = flavor
            return flavor

    def update_neutron_flavor(
        self,
        flavor_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> NeutronFlavor | None:
        """Update a Neutron service flavor."""
        with self._lock:
            flavor = self._neutron_flavors.get(flavor_id)
            if not flavor:
                return None
            if name is not None:
                flavor.name = name
            if description is not None:
                flavor.description = description
            if enabled is not None:
                flavor.enabled = enabled
            flavor.updated_at = datetime.now(timezone.utc)
            return flavor

    def delete_neutron_flavor(self, flavor_id: str) -> bool:
        """Delete a Neutron service flavor."""
        with self._lock:
            if flavor_id in self._neutron_flavors:
                del self._neutron_flavors[flavor_id]
                return True
            return False

    # Service Profiles

    def list_service_profiles(self) -> list[ServiceProfile]:
        """List Neutron service profiles."""
        with self._lock:
            return list(self._service_profiles.values())

    def get_service_profile(self, profile_id: str) -> ServiceProfile | None:
        """Get a service profile by ID."""
        with self._lock:
            return self._service_profiles.get(profile_id)


# Global database instance
db = Database()
