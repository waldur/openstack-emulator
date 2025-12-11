"""Data models for OpenStack emulator."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class VolumeStatus(str, Enum):
    """Volume status enumeration matching OpenStack Cinder states."""

    CREATING = "creating"
    AVAILABLE = "available"
    ATTACHING = "attaching"
    DETACHING = "detaching"
    IN_USE = "in-use"
    MAINTENANCE = "maintenance"
    DELETING = "deleting"
    AWAITING_TRANSFER = "awaiting-transfer"
    ERROR = "error"
    ERROR_DELETING = "error_deleting"
    BACKING_UP = "backing-up"
    RESTORING_BACKUP = "restoring-backup"
    ERROR_BACKING_UP = "error_backing-up"
    ERROR_RESTORING = "error_restoring"
    ERROR_EXTENDING = "error_extending"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    RETYPING = "retyping"
    EXTENDING = "extending"


class SnapshotStatus(str, Enum):
    """Snapshot status enumeration matching OpenStack Cinder states."""

    CREATING = "creating"
    AVAILABLE = "available"
    DELETING = "deleting"
    ERROR = "error"
    ERROR_DELETING = "error_deleting"


class ServerStatus(str, Enum):
    """Server status enumeration matching OpenStack Nova states."""

    ACTIVE = "ACTIVE"
    BUILD = "BUILD"
    DELETED = "DELETED"
    ERROR = "ERROR"
    HARD_REBOOT = "HARD_REBOOT"
    MIGRATING = "MIGRATING"
    PASSWORD = "PASSWORD"
    PAUSED = "PAUSED"
    REBOOT = "REBOOT"
    REBUILD = "REBUILD"
    RESCUE = "RESCUE"
    RESIZE = "RESIZE"
    REVERT_RESIZE = "REVERT_RESIZE"
    SHELVED = "SHELVED"
    SHELVED_OFFLOADED = "SHELVED_OFFLOADED"
    SHUTOFF = "SHUTOFF"
    SOFT_DELETED = "SOFT_DELETED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"
    VERIFY_RESIZE = "VERIFY_RESIZE"


class TaskState(str, Enum):
    """Server task state enumeration."""

    NONE = None  # type: ignore
    DELETING = "deleting"
    SOFT_DELETING = "soft-deleting"
    RESTORING = "restoring"
    SHELVING = "shelving"
    UNSHELVING = "unshelving"
    SPAWNING = "spawning"
    REBOOTING = "rebooting"
    REBOOTING_HARD = "rebooting_hard"
    POWERING_OFF = "powering-off"
    POWERING_ON = "powering-on"
    SUSPENDING = "suspending"
    RESUMING = "resuming"
    PAUSING = "pausing"
    UNPAUSING = "unpausing"
    REBUILDING = "rebuilding"
    RESIZING = "resizing"
    MIGRATING = "migrating"


class PowerState(int, Enum):
    """Server power state enumeration."""

    NO_STATE = 0
    RUNNING = 1
    PAUSED = 3
    SHUTDOWN = 4
    CRASHED = 6
    SUSPENDED = 7


@dataclass
class Flavor:
    """Represents a Nova flavor (instance type)."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    vcpus: int = 1
    ram: int = 512  # MB
    disk: int = 10  # GB
    ephemeral: int = 0  # GB
    swap: int = 0  # MB
    rxtx_factor: float = 1.0
    is_public: bool = True
    disabled: bool = False
    description: str = ""
    extra_specs: dict[str, str] = field(default_factory=dict)

    def to_dict(self, detailed: bool = True) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "links": [
                {"rel": "self", "href": f"/v2.1/flavors/{self.id}"},
                {"rel": "bookmark", "href": f"/flavors/{self.id}"},
            ],
        }
        if detailed:
            result.update(
                {
                    "vcpus": self.vcpus,
                    "ram": self.ram,
                    "disk": self.disk,
                    "OS-FLV-EXT-DATA:ephemeral": self.ephemeral,
                    "swap": self.swap if self.swap else "",
                    "rxtx_factor": self.rxtx_factor,
                    "os-flavor-access:is_public": self.is_public,
                    "OS-FLV-DISABLED:disabled": self.disabled,
                    "description": self.description,
                }
            )
        return result


class ImageStatus(str, Enum):
    """Image status enumeration matching OpenStack Glance states."""

    QUEUED = "queued"
    SAVING = "saving"
    ACTIVE = "active"
    KILLED = "killed"
    DELETED = "deleted"
    PENDING_DELETE = "pending_delete"
    DEACTIVATED = "deactivated"
    IMPORTING = "importing"
    UPLOADING = "uploading"


class ImageVisibility(str, Enum):
    """Image visibility enumeration."""

    PUBLIC = "public"
    PRIVATE = "private"
    SHARED = "shared"
    COMMUNITY = "community"


class ContainerFormat(str, Enum):
    """Container format enumeration."""

    AMI = "ami"
    ARI = "ari"
    AKI = "aki"
    BARE = "bare"
    OVF = "ovf"
    OVA = "ova"
    DOCKER = "docker"


class DiskFormat(str, Enum):
    """Disk format enumeration."""

    AMI = "ami"
    ARI = "ari"
    AKI = "aki"
    VHD = "vhd"
    VHDX = "vhdx"
    VMDK = "vmdk"
    RAW = "raw"
    QCOW2 = "qcow2"
    VDI = "vdi"
    ISO = "iso"
    PLOOP = "ploop"


@dataclass
class Image:
    """Represents a Glance image (simplified for Nova)."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: str = "ACTIVE"
    min_disk: int = 0  # GB
    min_ram: int = 0  # MB
    size: int = 0  # bytes
    created: datetime = field(default_factory=datetime.utcnow)
    updated: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self, detailed: bool = True) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "links": [
                {"rel": "self", "href": f"/v2.1/images/{self.id}"},
                {"rel": "bookmark", "href": f"/images/{self.id}"},
            ],
        }
        if detailed:
            result.update(
                {
                    "status": self.status,
                    "minDisk": self.min_disk,
                    "minRam": self.min_ram,
                    "OS-EXT-IMG-SIZE:size": self.size,
                    "created": self.created.isoformat() + "Z",
                    "updated": self.updated.isoformat() + "Z",
                    "metadata": self.metadata,
                }
            )
        return result


@dataclass
class GlanceImage:
    """Represents a Glance image with full API v2 properties."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: ImageStatus = ImageStatus.QUEUED
    visibility: ImageVisibility = ImageVisibility.PRIVATE
    protected: bool = False
    owner: str = ""  # project_id
    min_disk: int = 0  # GB
    min_ram: int = 0  # MB
    size: int | None = None  # bytes (None until image data uploaded)
    virtual_size: int | None = None
    checksum: str | None = None
    os_hash_algo: str | None = None
    os_hash_value: str | None = None
    os_hidden: bool = False
    container_format: ContainerFormat | None = None
    disk_format: DiskFormat | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)
    direct_url: str | None = None
    locations: list[dict[str, Any]] = field(default_factory=list)
    # Custom properties (user-defined metadata)
    properties: dict[str, Any] = field(default_factory=dict)
    # Architecture, OS info
    architecture: str | None = None
    os_distro: str | None = None
    os_version: str | None = None
    hw_disk_bus: str | None = None
    hw_vif_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to Glance API v2 response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "visibility": self.visibility.value,
            "protected": self.protected,
            "owner": self.owner,
            "min_disk": self.min_disk,
            "min_ram": self.min_ram,
            "os_hidden": self.os_hidden,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
            "tags": self.tags,
            "self": f"/v2/images/{self.id}",
            "file": f"/v2/images/{self.id}/file",
            "schema": "/v2/schemas/image",
        }

        # Add optional fields only if set
        if self.size is not None:
            result["size"] = self.size
        if self.virtual_size is not None:
            result["virtual_size"] = self.virtual_size
        if self.checksum is not None:
            result["checksum"] = self.checksum
        if self.os_hash_algo is not None:
            result["os_hash_algo"] = self.os_hash_algo
        if self.os_hash_value is not None:
            result["os_hash_value"] = self.os_hash_value
        if self.container_format is not None:
            result["container_format"] = self.container_format.value
        if self.disk_format is not None:
            result["disk_format"] = self.disk_format.value
        if self.direct_url is not None:
            result["direct_url"] = self.direct_url
        if self.locations:
            result["locations"] = self.locations
        if self.architecture:
            result["architecture"] = self.architecture
        if self.os_distro:
            result["os_distro"] = self.os_distro
        if self.os_version:
            result["os_version"] = self.os_version
        if self.hw_disk_bus:
            result["hw_disk_bus"] = self.hw_disk_bus
        if self.hw_vif_model:
            result["hw_vif_model"] = self.hw_vif_model

        # Add custom properties
        result.update(self.properties)

        return result

    def to_nova_image(self) -> Image:
        """Convert to Nova-compatible Image for compute API."""
        return Image(
            id=self.id,
            name=self.name,
            status=self.status.value.upper(),
            min_disk=self.min_disk,
            min_ram=self.min_ram,
            size=self.size or 0,
            created=self.created_at,
            updated=self.updated_at,
            metadata=dict(self.properties),
        )


@dataclass
class ImageMember:
    """Represents an image member (for image sharing)."""

    image_id: str = ""
    member_id: str = ""  # project_id that image is shared with
    status: str = "pending"  # pending, accepted, rejected
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    schema: str = "/v2/schemas/member"

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "image_id": self.image_id,
            "member_id": self.member_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
            "schema": self.schema,
        }


@dataclass
class Server:
    """Represents a Nova server instance."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: ServerStatus = ServerStatus.BUILD
    task_state: TaskState | None = None
    power_state: PowerState = PowerState.NO_STATE
    tenant_id: str = ""
    user_id: str = ""
    flavor_id: str = ""
    image_id: str = ""
    host: str = "compute-host-1"
    availability_zone: str = "nova"
    key_name: str | None = None
    created: datetime = field(default_factory=datetime.utcnow)
    updated: datetime = field(default_factory=datetime.utcnow)
    launched_at: datetime | None = None
    terminated_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    addresses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    security_groups: list[dict[str, str]] = field(
        default_factory=lambda: [{"name": "default"}]
    )
    admin_pass: str | None = None
    access_ipv4: str = ""
    access_ipv6: str = ""
    config_drive: str = ""
    progress: int = 0
    fault: dict[str, Any] | None = None

    def to_dict(self, detailed: bool = True) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "links": [
                {"rel": "self", "href": f"/v2.1/servers/{self.id}"},
                {"rel": "bookmark", "href": f"/servers/{self.id}"},
            ],
        }
        if detailed:
            result.update(
                {
                    "status": self.status.value,
                    "tenant_id": self.tenant_id,
                    "user_id": self.user_id,
                    "hostId": hash(self.host) % (10**16) if self.host else "",
                    "OS-EXT-SRV-ATTR:host": self.host,
                    "OS-EXT-SRV-ATTR:hypervisor_hostname": self.host,
                    "OS-EXT-SRV-ATTR:instance_name": f"instance-{self.id[:8]}",
                    "OS-EXT-STS:task_state": (
                        self.task_state.value if self.task_state else None
                    ),
                    "OS-EXT-STS:power_state": self.power_state.value,
                    "OS-EXT-STS:vm_state": self.status.value.lower(),
                    "OS-EXT-AZ:availability_zone": self.availability_zone,
                    "flavor": {
                        "id": self.flavor_id,
                        "links": [
                            {
                                "rel": "bookmark",
                                "href": f"/flavors/{self.flavor_id}",
                            }
                        ],
                    },
                    "image": (
                        {
                            "id": self.image_id,
                            "links": [
                                {
                                    "rel": "bookmark",
                                    "href": f"/images/{self.image_id}",
                                }
                            ],
                        }
                        if self.image_id
                        else ""
                    ),
                    "key_name": self.key_name,
                    "created": self.created.isoformat() + "Z",
                    "updated": self.updated.isoformat() + "Z",
                    "OS-SRV-USG:launched_at": (
                        self.launched_at.isoformat() + "Z" if self.launched_at else None
                    ),
                    "OS-SRV-USG:terminated_at": (
                        self.terminated_at.isoformat() + "Z"
                        if self.terminated_at
                        else None
                    ),
                    "metadata": self.metadata,
                    "addresses": self.addresses,
                    "security_groups": self.security_groups,
                    "accessIPv4": self.access_ipv4,
                    "accessIPv6": self.access_ipv6,
                    "config_drive": self.config_drive,
                    "progress": self.progress,
                }
            )
            if self.fault:
                result["fault"] = self.fault
        return result


@dataclass
class Keypair:
    """Represents an SSH keypair."""

    name: str = ""
    public_key: str = ""
    fingerprint: str = ""
    user_id: str = ""
    type: str = "ssh"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "name": self.name,
            "public_key": self.public_key,
            "fingerprint": self.fingerprint,
            "user_id": self.user_id,
            "type": self.type,
            "created_at": self.created_at.isoformat() + "Z",
        }


@dataclass
class Token:
    """Represents a Keystone authentication token."""

    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    user_name: str = ""
    project_id: str = ""
    project_name: str = ""
    domain_id: str = "default"
    domain_name: str = "Default"
    roles: list[dict[str, str]] = field(
        default_factory=lambda: [{"id": "admin", "name": "admin"}]
    )
    issued_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    catalog: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "token": {
                "methods": ["password"],
                "user": {
                    "id": self.user_id,
                    "name": self.user_name,
                    "domain": {"id": self.domain_id, "name": self.domain_name},
                },
                "project": {
                    "id": self.project_id,
                    "name": self.project_name,
                    "domain": {"id": self.domain_id, "name": self.domain_name},
                },
                "roles": self.roles,
                "issued_at": self.issued_at.isoformat() + "Z",
                "expires_at": (
                    self.expires_at.isoformat() + "Z" if self.expires_at else None
                ),
                "catalog": self.catalog,
            }
        }


# Keystone Identity Models


@dataclass
class Domain:
    """Represents a Keystone domain."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "tags": self.tags,
            "links": {"self": f"/v3/domains/{self.id}"},
        }


@dataclass
class Project:
    """Represents a Keystone project."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    domain_id: str = "default"
    parent_id: str | None = None
    enabled: bool = True
    is_domain: bool = False
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain_id": self.domain_id,
            "enabled": self.enabled,
            "is_domain": self.is_domain,
            "tags": self.tags,
            "links": {"self": f"/v3/projects/{self.id}"},
        }
        if self.parent_id:
            result["parent_id"] = self.parent_id
        return result


@dataclass
class User:
    """Represents a Keystone user."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    domain_id: str = "default"
    default_project_id: str | None = None
    enabled: bool = True
    password_hash: str = ""
    email: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain_id": self.domain_id,
            "enabled": self.enabled,
            "email": self.email,
            "links": {"self": f"/v3/users/{self.id}"},
        }
        if self.default_project_id:
            result["default_project_id"] = self.default_project_id
        return result


@dataclass
class Role:
    """Represents a Keystone role."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    domain_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "links": {"self": f"/v3/roles/{self.id}"},
        }
        if self.domain_id:
            result["domain_id"] = self.domain_id
        return result


@dataclass
class RoleAssignment:
    """Represents a role assignment to a user/group on a project/domain."""

    role_id: str = ""
    user_id: str | None = None
    group_id: str | None = None
    project_id: str | None = None
    domain_id: str | None = None
    inherited: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "role": {"id": self.role_id},
            "links": {"assignment": "/v3/role_assignments"},
        }
        if self.user_id:
            result["user"] = {"id": self.user_id}
        if self.group_id:
            result["group"] = {"id": self.group_id}
        if self.project_id:
            result["scope"] = {"project": {"id": self.project_id}}
        elif self.domain_id:
            result["scope"] = {"domain": {"id": self.domain_id}}
        return result


@dataclass
class Group:
    """Represents a Keystone group."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    domain_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain_id": self.domain_id,
            "links": {"self": f"/v3/groups/{self.id}"},
        }


@dataclass
class Service:
    """Represents a Keystone service."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    type: str = ""
    description: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "enabled": self.enabled,
            "links": {"self": f"/v3/services/{self.id}"},
        }


@dataclass
class Endpoint:
    """Represents a Keystone endpoint."""

    id: str = field(default_factory=lambda: str(uuid4()))
    service_id: str = ""
    interface: str = "public"  # public, internal, admin
    url: str = ""
    region_id: str | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "service_id": self.service_id,
            "interface": self.interface,
            "url": self.url,
            "enabled": self.enabled,
            "links": {"self": f"/v3/endpoints/{self.id}"},
        }
        if self.region_id:
            result["region_id"] = self.region_id
            result["region"] = self.region_id
        return result


@dataclass
class Region:
    """Represents a Keystone region."""

    id: str = ""
    description: str = ""
    parent_region_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "links": {"self": f"/v3/regions/{self.id}"},
        }
        if self.parent_region_id:
            result["parent_region_id"] = self.parent_region_id
        return result


@dataclass
class Credential:
    """Represents a Keystone credential (e.g., EC2-style)."""

    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    project_id: str | None = None
    type: str = "ec2"  # ec2, cert, etc.
    blob: str = ""  # JSON-encoded credential data

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "blob": self.blob,
            "links": {"self": f"/v3/credentials/{self.id}"},
        }
        if self.project_id:
            result["project_id"] = self.project_id
        return result


# Cinder Block Storage Models


@dataclass
class VolumeType:
    """Represents a Cinder volume type."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    is_public: bool = True
    extra_specs: dict[str, str] = field(default_factory=dict)
    qos_specs_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_public": self.is_public,
            "extra_specs": self.extra_specs,
            "qos_specs_id": self.qos_specs_id,
        }


@dataclass
class VolumeAttachment:
    """Represents a volume attachment to a server."""

    id: str = field(default_factory=lambda: str(uuid4()))
    volume_id: str = ""
    server_id: str = ""
    device: str = ""  # e.g., /dev/vdb
    attached_at: datetime = field(default_factory=datetime.utcnow)
    host_name: str = ""
    attachment_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "volume_id": self.volume_id,
            "server_id": self.server_id,
            "device": self.device,
            "attached_at": self.attached_at.isoformat() + "Z",
            "host_name": self.host_name,
            "attachment_id": self.attachment_id,
        }


@dataclass
class Volume:
    """Represents a Cinder volume."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: VolumeStatus = VolumeStatus.CREATING
    size: int = 1  # GB
    volume_type: str = "lvmdriver-1"
    availability_zone: str = "nova"
    bootable: bool = False
    encrypted: bool = False
    multiattach: bool = False
    source_volid: str | None = None
    snapshot_id: str | None = None
    image_id: str | None = None
    project_id: str = ""
    user_id: str = ""
    host: str | None = None
    attachments: list[VolumeAttachment] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    migration_status: str | None = None
    replication_status: str | None = None
    consistencygroup_id: str | None = None
    group_id: str | None = None

    def to_dict(self, detailed: bool = True) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "links": [
                {"rel": "self", "href": f"/v3/volumes/{self.id}"},
                {"rel": "bookmark", "href": f"/volumes/{self.id}"},
            ],
        }
        if detailed:
            result.update(
                {
                    "description": self.description,
                    "status": self.status.value,
                    "size": self.size,
                    "volume_type": self.volume_type,
                    "availability_zone": self.availability_zone,
                    "bootable": str(self.bootable).lower(),
                    "encrypted": self.encrypted,
                    "multiattach": self.multiattach,
                    "source_volid": self.source_volid,
                    "snapshot_id": self.snapshot_id,
                    "image_id": self.image_id,
                    "os-vol-tenant-attr:tenant_id": self.project_id,
                    "user_id": self.user_id,
                    "os-vol-host-attr:host": self.host,
                    "attachments": [a.to_dict() for a in self.attachments],
                    "metadata": self.metadata,
                    "created_at": self.created_at.isoformat() + "Z",
                    "updated_at": self.updated_at.isoformat() + "Z",
                    "migration_status": self.migration_status,
                    "replication_status": self.replication_status,
                    "consistencygroup_id": self.consistencygroup_id,
                    "group_id": self.group_id,
                }
            )
        return result


@dataclass
class Snapshot:
    """Represents a Cinder volume snapshot."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: SnapshotStatus = SnapshotStatus.CREATING
    volume_id: str = ""
    size: int = 0  # GB (inherited from volume)
    project_id: str = ""
    user_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    progress: str = "0%"

    def to_dict(self, detailed: bool = True) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "links": [
                {"rel": "self", "href": f"/v3/snapshots/{self.id}"},
                {"rel": "bookmark", "href": f"/snapshots/{self.id}"},
            ],
        }
        if detailed:
            result.update(
                {
                    "description": self.description,
                    "status": self.status.value,
                    "volume_id": self.volume_id,
                    "size": self.size,
                    "os-extended-snapshot-attributes:project_id": self.project_id,
                    "user_id": self.user_id,
                    "metadata": self.metadata,
                    "created_at": self.created_at.isoformat() + "Z",
                    "updated_at": self.updated_at.isoformat() + "Z",
                    "os-extended-snapshot-attributes:progress": self.progress,
                }
            )
        return result


@dataclass
class QosSpec:
    """Represents a Cinder QoS specification."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    consumer: str = "both"  # front-end, back-end, both
    specs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "consumer": self.consumer,
            "specs": self.specs,
        }
