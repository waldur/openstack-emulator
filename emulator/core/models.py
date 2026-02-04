"""Data models for OpenStack emulator."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def format_datetime_utc(dt: datetime) -> str:
    """Format datetime as ISO8601 UTC string.

    Args:
        dt: datetime object (timezone-aware or naive)

    Returns:
        ISO8601 string with Z suffix for UTC timezone
    """
    if dt.tzinfo is not None and dt.tzinfo == timezone.utc:
        # For timezone-aware UTC datetime, use isoformat but replace +00:00 with Z
        return dt.isoformat().replace("+00:00", "Z")
    else:
        # For naive datetime (assumed to be UTC), append Z
        return dt.isoformat() + "Z"


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
                    "created": format_datetime_utc(self.created),
                    "updated": format_datetime_utc(self.updated),
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
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
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
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
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
    security_groups: list[dict[str, str]] = field(default_factory=lambda: [{"name": "default"}])
    admin_pass: str | None = None
    access_ipv4: str = ""
    access_ipv6: str = ""
    config_drive: str = ""
    progress: int = 0
    fault: dict[str, Any] | None = None
    # Resize tracking: stores original flavor_id during resize for revert
    original_flavor_id: str | None = None
    # Stores the status before resize to restore on confirm/revert
    pre_resize_status: ServerStatus | None = None

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
                    "OS-EXT-STS:task_state": (self.task_state.value if self.task_state else None),
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
                    "created": format_datetime_utc(self.created),
                    "updated": format_datetime_utc(self.updated),
                    "OS-SRV-USG:launched_at": (
                        format_datetime_utc(self.launched_at) if self.launched_at else None
                    ),
                    "OS-SRV-USG:terminated_at": (
                        format_datetime_utc(self.terminated_at) if self.terminated_at else None
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
            "created_at": format_datetime_utc(self.created_at),
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
    roles: list[dict[str, str]] = field(default_factory=lambda: [{"id": "admin", "name": "admin"}])
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
                "issued_at": format_datetime_utc(self.issued_at),
                "expires_at": (format_datetime_utc(self.expires_at) if self.expires_at else None),
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
    options: dict[str, Any] = field(default_factory=dict)

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
            "options": self.options,
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
            "os-volume-type-access:is_public": self.is_public,  # Additional field for compatibility
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
            "attached_at": format_datetime_utc(self.attached_at),
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
                    "created_at": format_datetime_utc(self.created_at),
                    "updated_at": format_datetime_utc(self.updated_at),
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
                    "created_at": format_datetime_utc(self.created_at),
                    "updated_at": format_datetime_utc(self.updated_at),
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


# Neutron Networking Models


class NetworkStatus(str, Enum):
    """Network status enumeration."""

    ACTIVE = "ACTIVE"
    DOWN = "DOWN"
    BUILD = "BUILD"
    ERROR = "ERROR"


class PortStatus(str, Enum):
    """Port status enumeration."""

    ACTIVE = "ACTIVE"
    DOWN = "DOWN"
    BUILD = "BUILD"
    ERROR = "ERROR"


class RouterStatus(str, Enum):
    """Router status enumeration."""

    ACTIVE = "ACTIVE"
    ALLOCATING = "ALLOCATING"
    ERROR = "ERROR"


class FloatingIPStatus(str, Enum):
    """Floating IP status enumeration."""

    ACTIVE = "ACTIVE"
    DOWN = "DOWN"
    ERROR = "ERROR"


@dataclass
class Network:
    """Represents a Neutron network."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: NetworkStatus = NetworkStatus.ACTIVE
    admin_state_up: bool = True
    shared: bool = False
    external: bool = False  # router:external
    project_id: str = ""
    mtu: int = 1500
    port_security_enabled: bool = True
    provider_network_type: str | None = None  # flat, vlan, vxlan, gre
    provider_physical_network: str | None = None
    provider_segmentation_id: int | None = None
    availability_zone_hints: list[str] = field(default_factory=list)
    availability_zones: list[str] = field(default_factory=lambda: ["nova"])
    dns_domain: str = ""
    subnets: list[str] = field(default_factory=list)  # subnet IDs
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "admin_state_up": self.admin_state_up,
            "shared": self.shared,
            "router:external": self.external,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "mtu": self.mtu,
            "port_security_enabled": self.port_security_enabled,
            "provider:network_type": self.provider_network_type,
            "provider:physical_network": self.provider_physical_network,
            "provider:segmentation_id": self.provider_segmentation_id,
            "availability_zone_hints": self.availability_zone_hints,
            "availability_zones": self.availability_zones,
            "dns_domain": self.dns_domain,
            "subnets": self.subnets,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class AllocationPool:
    """Represents an IP allocation pool for a subnet."""

    start: str = ""
    end: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to API response format."""
        return {"start": self.start, "end": self.end}


@dataclass
class Subnet:
    """Represents a Neutron subnet."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    network_id: str = ""
    ip_version: int = 4  # 4 or 6
    cidr: str = ""
    gateway_ip: str | None = None
    allocation_pools: list[AllocationPool] = field(default_factory=list)
    dns_nameservers: list[str] = field(default_factory=list)
    host_routes: list[dict[str, str]] = field(default_factory=list)
    enable_dhcp: bool = True
    project_id: str = ""
    ipv6_ra_mode: str | None = None  # slaac, dhcpv6-stateful, dhcpv6-stateless
    ipv6_address_mode: str | None = None
    subnetpool_id: str | None = None
    service_types: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "network_id": self.network_id,
            "ip_version": self.ip_version,
            "cidr": self.cidr,
            "gateway_ip": self.gateway_ip,
            "allocation_pools": [p.to_dict() for p in self.allocation_pools],
            "dns_nameservers": self.dns_nameservers,
            "host_routes": self.host_routes,
            "enable_dhcp": self.enable_dhcp,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "ipv6_ra_mode": self.ipv6_ra_mode,
            "ipv6_address_mode": self.ipv6_address_mode,
            "subnetpool_id": self.subnetpool_id,
            "service_types": self.service_types,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class FixedIP:
    """Represents a fixed IP address on a port."""

    subnet_id: str = ""
    ip_address: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to API response format."""
        return {"subnet_id": self.subnet_id, "ip_address": self.ip_address}


@dataclass
class Port:
    """Represents a Neutron port."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    network_id: str = ""
    status: PortStatus = PortStatus.ACTIVE
    admin_state_up: bool = True
    mac_address: str = ""
    fixed_ips: list[FixedIP] = field(default_factory=list)
    device_id: str = ""  # server ID if attached
    device_owner: str = ""  # compute:nova, network:router_interface, etc.
    project_id: str = ""
    security_groups: list[str] = field(default_factory=list)
    port_security_enabled: bool = True
    allowed_address_pairs: list[dict[str, str]] = field(default_factory=list)
    extra_dhcp_opts: list[dict[str, str]] = field(default_factory=list)
    binding_host_id: str = ""
    binding_vnic_type: str = "normal"  # normal, direct, macvtap, etc.
    binding_vif_type: str = ""
    binding_profile: dict[str, Any] = field(default_factory=dict)
    binding_vif_details: dict[str, Any] = field(default_factory=dict)
    dns_name: str = ""
    dns_assignment: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "network_id": self.network_id,
            "status": self.status.value,
            "admin_state_up": self.admin_state_up,
            "mac_address": self.mac_address,
            "fixed_ips": [ip.to_dict() for ip in self.fixed_ips],
            "device_id": self.device_id,
            "device_owner": self.device_owner,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "security_groups": self.security_groups,
            "port_security_enabled": self.port_security_enabled,
            "allowed_address_pairs": self.allowed_address_pairs,
            "extra_dhcp_opts": self.extra_dhcp_opts,
            "binding:host_id": self.binding_host_id,
            "binding:vnic_type": self.binding_vnic_type,
            "binding:vif_type": self.binding_vif_type,
            "binding:profile": self.binding_profile,
            "binding:vif_details": self.binding_vif_details,
            "dns_name": self.dns_name,
            "dns_assignment": self.dns_assignment,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class ExternalGatewayInfo:
    """Represents external gateway info for a router."""

    network_id: str = ""
    enable_snat: bool = True
    external_fixed_ips: list[FixedIP] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "network_id": self.network_id,
            "enable_snat": self.enable_snat,
            "external_fixed_ips": [ip.to_dict() for ip in self.external_fixed_ips],
        }


@dataclass
class Router:
    """Represents a Neutron router."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: RouterStatus = RouterStatus.ACTIVE
    admin_state_up: bool = True
    project_id: str = ""
    external_gateway_info: ExternalGatewayInfo | None = None
    routes: list[dict[str, str]] = field(default_factory=list)  # static routes
    availability_zone_hints: list[str] = field(default_factory=list)
    availability_zones: list[str] = field(default_factory=list)
    ha: bool = False
    distributed: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "admin_state_up": self.admin_state_up,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "routes": self.routes,
            "availability_zone_hints": self.availability_zone_hints,
            "availability_zones": self.availability_zones,
            "ha": self.ha,
            "distributed": self.distributed,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }
        if self.external_gateway_info:
            result["external_gateway_info"] = self.external_gateway_info.to_dict()
        else:
            result["external_gateway_info"] = None
        return result


@dataclass
class FloatingIP:
    """Represents a Neutron floating IP."""

    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    status: FloatingIPStatus = FloatingIPStatus.DOWN
    floating_network_id: str = ""
    floating_ip_address: str = ""
    fixed_ip_address: str | None = None
    port_id: str | None = None  # The internal port this FIP is associated with
    floating_port_id: str | None = None  # The port on external network holding the FIP
    router_id: str | None = None
    project_id: str = ""
    dns_domain: str = ""
    dns_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "floating_network_id": self.floating_network_id,
            "floating_ip_address": self.floating_ip_address,
            "fixed_ip_address": self.fixed_ip_address,
            "port_id": self.port_id,
            "floating_port_id": self.floating_port_id,
            "router_id": self.router_id,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "dns_domain": self.dns_domain,
            "dns_name": self.dns_name,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class SecurityGroupRule:
    """Represents a Neutron security group rule."""

    id: str = field(default_factory=lambda: str(uuid4()))
    security_group_id: str = ""
    direction: str = "ingress"  # ingress or egress
    ethertype: str = "IPv4"  # IPv4 or IPv6
    protocol: str | None = None  # tcp, udp, icmp, etc.
    port_range_min: int | None = None
    port_range_max: int | None = None
    remote_ip_prefix: str | None = None
    remote_group_id: str | None = None
    remote_address_group_id: str | None = None
    description: str = ""
    project_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "security_group_id": self.security_group_id,
            "direction": self.direction,
            "ethertype": self.ethertype,
            "protocol": self.protocol,
            "port_range_min": self.port_range_min,
            "port_range_max": self.port_range_max,
            "remote_ip_prefix": self.remote_ip_prefix,
            "remote_group_id": self.remote_group_id,
            "remote_address_group_id": self.remote_address_group_id,
            "description": self.description,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "revision_number": 1,
        }


@dataclass
class SecurityGroup:
    """Represents a Neutron security group."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    project_id: str = ""
    security_group_rules: list[SecurityGroupRule] = field(default_factory=list)
    stateful: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "security_group_rules": [r.to_dict() for r in self.security_group_rules],
            "stateful": self.stateful,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


# Nova Server Groups


@dataclass
class ServerGroup:
    """Represents a Nova server group for affinity/anti-affinity policies."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    policies: list[str] = field(
        default_factory=list
    )  # affinity, anti-affinity, soft-affinity, soft-anti-affinity
    members: list[str] = field(default_factory=list)  # server IDs
    project_id: str = ""
    user_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "policies": self.policies,
            "members": self.members,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


# Quota Models


@dataclass
class NovaQuota:
    """Represents Nova compute quotas for a project."""

    project_id: str = ""
    instances: int = 10
    cores: int = 20
    ram: int = 51200  # MB
    metadata_items: int = 128
    injected_files: int = 5
    injected_file_content_bytes: int = 10240
    injected_file_path_bytes: int = 255
    key_pairs: int = 100
    server_groups: int = 10
    server_group_members: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.project_id,
            "instances": self.instances,
            "cores": self.cores,
            "ram": self.ram,
            "metadata_items": self.metadata_items,
            "injected_files": self.injected_files,
            "injected_file_content_bytes": self.injected_file_content_bytes,
            "injected_file_path_bytes": self.injected_file_path_bytes,
            "key_pairs": self.key_pairs,
            "server_groups": self.server_groups,
            "server_group_members": self.server_group_members,
        }


@dataclass
class NeutronQuota:
    """Represents Neutron networking quotas for a project."""

    project_id: str = ""
    network: int = 100
    subnet: int = 100
    subnetpool: int = -1
    port: int = 500
    router: int = 10
    floatingip: int = 50
    security_group: int = 10
    security_group_rule: int = 100
    rbac_policy: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "network": self.network,
            "subnet": self.subnet,
            "subnetpool": self.subnetpool,
            "port": self.port,
            "router": self.router,
            "floatingip": self.floatingip,
            "security_group": self.security_group,
            "security_group_rule": self.security_group_rule,
            "rbac_policy": self.rbac_policy,
        }

    def to_detail_dict(self, usage: dict[str, int]) -> dict[str, Any]:
        """Convert to detailed quota response with usage."""
        return {
            "network": {"limit": self.network, "used": usage.get("network", 0), "reserved": 0},
            "subnet": {"limit": self.subnet, "used": usage.get("subnet", 0), "reserved": 0},
            "subnetpool": {
                "limit": self.subnetpool,
                "used": usage.get("subnetpool", 0),
                "reserved": 0,
            },
            "port": {"limit": self.port, "used": usage.get("port", 0), "reserved": 0},
            "router": {"limit": self.router, "used": usage.get("router", 0), "reserved": 0},
            "floatingip": {
                "limit": self.floatingip,
                "used": usage.get("floatingip", 0),
                "reserved": 0,
            },
            "security_group": {
                "limit": self.security_group,
                "used": usage.get("security_group", 0),
                "reserved": 0,
            },
            "security_group_rule": {
                "limit": self.security_group_rule,
                "used": usage.get("security_group_rule", 0),
                "reserved": 0,
            },
            "rbac_policy": {
                "limit": self.rbac_policy,
                "used": usage.get("rbac_policy", 0),
                "reserved": 0,
            },
        }


@dataclass
class CinderQuota:
    """Represents Cinder block storage quotas for a project."""

    project_id: str = ""
    volumes: int = 10
    snapshots: int = 10
    gigabytes: int = 1000  # GB
    per_volume_gigabytes: int = -1  # -1 means unlimited
    backups: int = 10
    backup_gigabytes: int = 1000
    groups: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.project_id,
            "volumes": self.volumes,
            "snapshots": self.snapshots,
            "gigabytes": self.gigabytes,
            "per_volume_gigabytes": self.per_volume_gigabytes,
            "backups": self.backups,
            "backup_gigabytes": self.backup_gigabytes,
            "groups": self.groups,
        }


# Neutron RBAC Policy Models


class RbacAction(str, Enum):
    """RBAC action types."""

    ACCESS_AS_SHARED = "access_as_shared"
    ACCESS_AS_EXTERNAL = "access_as_external"


@dataclass
class RbacPolicy:
    """Represents a Neutron RBAC policy for sharing resources between tenants."""

    id: str = field(default_factory=lambda: str(uuid4()))
    object_type: str = (
        "network"  # network, qos_policy, security_group, address_scope, subnetpool, address_group
    )
    object_id: str = ""
    target_project: str = ""  # '*' for all tenants or specific project_id
    project_id: str = ""  # owner of the policy
    action: str = "access_as_shared"  # access_as_shared, access_as_external
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "target_tenant": self.target_project,  # Neutron API uses target_tenant
            "target_project": self.target_project,
            "tenant_id": self.project_id,
            "project_id": self.project_id,
            "action": self.action,
        }


# Octavia Load Balancer Models


class LoadBalancerProvisioningStatus(str, Enum):
    """Load balancer provisioning status enumeration."""

    ACTIVE = "ACTIVE"
    DELETED = "DELETED"
    ERROR = "ERROR"
    PENDING_CREATE = "PENDING_CREATE"
    PENDING_UPDATE = "PENDING_UPDATE"
    PENDING_DELETE = "PENDING_DELETE"


class LoadBalancerOperatingStatus(str, Enum):
    """Load balancer operating status enumeration."""

    ONLINE = "ONLINE"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    NO_MONITOR = "NO_MONITOR"


class ListenerProtocol(str, Enum):
    """Listener protocol enumeration."""

    HTTP = "HTTP"
    HTTPS = "HTTPS"
    TCP = "TCP"
    TERMINATED_HTTPS = "TERMINATED_HTTPS"
    UDP = "UDP"
    SCTP = "SCTP"
    PROMETHEUS = "PROMETHEUS"


class PoolProtocol(str, Enum):
    """Pool protocol enumeration."""

    HTTP = "HTTP"
    HTTPS = "HTTPS"
    PROXY = "PROXY"
    PROXYV2 = "PROXYV2"
    TCP = "TCP"
    UDP = "UDP"
    SCTP = "SCTP"


class PoolLBAlgorithm(str, Enum):
    """Pool load balancing algorithm enumeration."""

    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_CONNECTIONS = "LEAST_CONNECTIONS"
    SOURCE_IP = "SOURCE_IP"
    SOURCE_IP_PORT = "SOURCE_IP_PORT"


class HealthMonitorType(str, Enum):
    """Health monitor type enumeration."""

    HTTP = "HTTP"
    HTTPS = "HTTPS"
    PING = "PING"
    TCP = "TCP"
    TLS_HELLO = "TLS-HELLO"
    UDP_CONNECT = "UDP-CONNECT"
    SCTP = "SCTP"


class L7PolicyAction(str, Enum):
    """L7 policy action enumeration."""

    REJECT = "REJECT"
    REDIRECT_TO_POOL = "REDIRECT_TO_POOL"
    REDIRECT_TO_URL = "REDIRECT_TO_URL"
    REDIRECT_PREFIX = "REDIRECT_PREFIX"


class L7RuleType(str, Enum):
    """L7 rule type enumeration."""

    COOKIE = "COOKIE"
    FILE_TYPE = "FILE_TYPE"
    HEADER = "HEADER"
    HOST_NAME = "HOST_NAME"
    PATH = "PATH"
    SSL_CONN_HAS_CERT = "SSL_CONN_HAS_CERT"
    SSL_VERIFY_RESULT = "SSL_VERIFY_RESULT"
    SSL_DN_FIELD = "SSL_DN_FIELD"


class L7RuleCompareType(str, Enum):
    """L7 rule compare type enumeration."""

    CONTAINS = "CONTAINS"
    ENDS_WITH = "ENDS_WITH"
    EQUAL_TO = "EQUAL_TO"
    REGEX = "REGEX"
    STARTS_WITH = "STARTS_WITH"


@dataclass
class HealthMonitor:
    """Represents an Octavia health monitor."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    type: HealthMonitorType = HealthMonitorType.HTTP
    delay: int = 5  # seconds between health checks
    timeout: int = 5  # seconds to wait for response
    max_retries: int = 3
    max_retries_down: int = 3
    http_method: str = "GET"
    url_path: str = "/"
    expected_codes: str = "200"
    admin_state_up: bool = True
    pool_id: str = ""
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "delay": self.delay,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "max_retries_down": self.max_retries_down,
            "http_method": self.http_method,
            "url_path": self.url_path,
            "expected_codes": self.expected_codes,
            "admin_state_up": self.admin_state_up,
            "pool_id": self.pool_id,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


@dataclass
class PoolMember:
    """Represents an Octavia pool member."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    address: str = ""
    protocol_port: int = 80
    weight: int = 1
    subnet_id: str | None = None
    admin_state_up: bool = True
    pool_id: str = ""
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    backup: bool = False
    monitor_address: str | None = None
    monitor_port: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "protocol_port": self.protocol_port,
            "weight": self.weight,
            "subnet_id": self.subnet_id,
            "admin_state_up": self.admin_state_up,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "backup": self.backup,
            "monitor_address": self.monitor_address,
            "monitor_port": self.monitor_port,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


@dataclass
class Pool:
    """Represents an Octavia pool."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    protocol: PoolProtocol = PoolProtocol.HTTP
    lb_algorithm: PoolLBAlgorithm = PoolLBAlgorithm.ROUND_ROBIN
    admin_state_up: bool = True
    loadbalancer_id: str | None = None
    listener_id: str | None = None
    healthmonitor_id: str | None = None
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    members: list[PoolMember] = field(default_factory=list)
    session_persistence: dict[str, Any] | None = None
    tls_container_ref: str | None = None
    ca_tls_container_ref: str | None = None
    crl_container_ref: str | None = None
    tls_enabled: bool = False
    tls_ciphers: str | None = None
    tls_versions: list[str] | None = None
    alpn_protocols: list[str] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol.value,
            "lb_algorithm": self.lb_algorithm.value,
            "admin_state_up": self.admin_state_up,
            "loadbalancers": ([{"id": self.loadbalancer_id}] if self.loadbalancer_id else []),
            "listeners": [{"id": self.listener_id}] if self.listener_id else [],
            "healthmonitor_id": self.healthmonitor_id,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "members": [m.to_dict() for m in self.members],
            "session_persistence": self.session_persistence,
            "tls_container_ref": self.tls_container_ref,
            "ca_tls_container_ref": self.ca_tls_container_ref,
            "crl_container_ref": self.crl_container_ref,
            "tls_enabled": self.tls_enabled,
            "tls_ciphers": self.tls_ciphers,
            "tls_versions": self.tls_versions,
            "alpn_protocols": self.alpn_protocols,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }
        return result


@dataclass
class L7Rule:
    """Represents an Octavia L7 rule."""

    id: str = field(default_factory=lambda: str(uuid4()))
    type: L7RuleType = L7RuleType.PATH
    compare_type: L7RuleCompareType = L7RuleCompareType.EQUAL_TO
    key: str | None = None
    value: str = ""
    invert: bool = False
    admin_state_up: bool = True
    l7policy_id: str = ""
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "type": self.type.value,
            "compare_type": self.compare_type.value,
            "key": self.key,
            "value": self.value,
            "invert": self.invert,
            "admin_state_up": self.admin_state_up,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


@dataclass
class L7Policy:
    """Represents an Octavia L7 policy."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    action: L7PolicyAction = L7PolicyAction.REJECT
    redirect_pool_id: str | None = None
    redirect_url: str | None = None
    redirect_prefix: str | None = None
    redirect_http_code: int | None = None
    position: int = 1
    admin_state_up: bool = True
    listener_id: str = ""
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    rules: list[L7Rule] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "action": self.action.value,
            "redirect_pool_id": self.redirect_pool_id,
            "redirect_url": self.redirect_url,
            "redirect_prefix": self.redirect_prefix,
            "redirect_http_code": self.redirect_http_code,
            "position": self.position,
            "admin_state_up": self.admin_state_up,
            "listener_id": self.listener_id,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "rules": [r.to_dict() for r in self.rules],
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


@dataclass
class Listener:
    """Represents an Octavia listener."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    protocol: ListenerProtocol = ListenerProtocol.HTTP
    protocol_port: int = 80
    connection_limit: int = -1  # -1 means unlimited
    default_pool_id: str | None = None
    admin_state_up: bool = True
    loadbalancer_id: str = ""
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    default_tls_container_ref: str | None = None
    sni_container_refs: list[str] = field(default_factory=list)
    client_authentication: str = "NONE"  # NONE, OPTIONAL, MANDATORY
    client_ca_tls_container_ref: str | None = None
    client_crl_container_ref: str | None = None
    insert_headers: dict[str, str] = field(default_factory=dict)
    timeout_client_data: int | None = None
    timeout_member_connect: int | None = None
    timeout_member_data: int | None = None
    timeout_tcp_inspect: int | None = None
    allowed_cidrs: list[str] | None = None
    tls_ciphers: str | None = None
    tls_versions: list[str] | None = None
    alpn_protocols: list[str] | None = None
    l7policies: list[L7Policy] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol.value,
            "protocol_port": self.protocol_port,
            "connection_limit": self.connection_limit,
            "default_pool_id": self.default_pool_id,
            "admin_state_up": self.admin_state_up,
            "loadbalancers": [{"id": self.loadbalancer_id}],
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "default_tls_container_ref": self.default_tls_container_ref,
            "sni_container_refs": self.sni_container_refs,
            "client_authentication": self.client_authentication,
            "client_ca_tls_container_ref": self.client_ca_tls_container_ref,
            "client_crl_container_ref": self.client_crl_container_ref,
            "insert_headers": self.insert_headers,
            "timeout_client_data": self.timeout_client_data,
            "timeout_member_connect": self.timeout_member_connect,
            "timeout_member_data": self.timeout_member_data,
            "timeout_tcp_inspect": self.timeout_tcp_inspect,
            "allowed_cidrs": self.allowed_cidrs,
            "tls_ciphers": self.tls_ciphers,
            "tls_versions": self.tls_versions,
            "alpn_protocols": self.alpn_protocols,
            "l7policies": [p.to_dict() for p in self.l7policies],
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


@dataclass
class LoadBalancer:
    """Represents an Octavia load balancer."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    admin_state_up: bool = True
    vip_subnet_id: str | None = None
    vip_network_id: str | None = None
    vip_port_id: str | None = None
    vip_address: str = ""
    vip_qos_policy_id: str | None = None
    flavor_id: str | None = None
    availability_zone: str | None = None
    provider: str = "amphora"
    project_id: str = ""
    provisioning_status: LoadBalancerProvisioningStatus = LoadBalancerProvisioningStatus.ACTIVE
    operating_status: LoadBalancerOperatingStatus = LoadBalancerOperatingStatus.ONLINE
    listeners: list[Listener] = field(default_factory=list)
    pools: list[Pool] = field(default_factory=list)
    additional_vips: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "admin_state_up": self.admin_state_up,
            "vip_subnet_id": self.vip_subnet_id,
            "vip_network_id": self.vip_network_id,
            "vip_port_id": self.vip_port_id,
            "vip_address": self.vip_address,
            "vip_qos_policy_id": self.vip_qos_policy_id,
            "flavor_id": self.flavor_id,
            "availability_zone": self.availability_zone,
            "provider": self.provider,
            "project_id": self.project_id,
            "provisioning_status": self.provisioning_status.value,
            "operating_status": self.operating_status.value,
            "listeners": [{"id": listener.id} for listener in self.listeners],
            "pools": [{"id": pool.id} for pool in self.pools],
            "additional_vips": self.additional_vips,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
        }


# Nova Extensions and Additional Models


@dataclass
class ServerVolumeAttachment:
    """Represents a volume attachment to a server."""

    id: str = field(default_factory=lambda: str(uuid4()))
    volume_id: str = ""
    server_id: str = ""
    device: str | None = None  # e.g., /dev/vdb
    attachment_id: str = field(default_factory=lambda: str(uuid4()))
    tag: str | None = None
    delete_on_termination: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.attachment_id,
            "volumeId": self.volume_id,
            "serverId": self.server_id,
            "device": self.device,
            "tag": self.tag,
            "delete_on_termination": self.delete_on_termination,
        }


@dataclass
class ServerNetworkInterface:
    """Represents a network interface attached to a server."""

    port_id: str = field(default_factory=lambda: str(uuid4()))
    net_id: str = ""
    mac_addr: str = ""
    port_state: str = "ACTIVE"  # ACTIVE, DOWN, BUILD, ERROR
    fixed_ips: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "port_id": self.port_id,
            "net_id": self.net_id,
            "mac_addr": self.mac_addr,
            "port_state": self.port_state,
            "fixed_ips": self.fixed_ips,
        }


@dataclass
class ServerConsole:
    """Represents a console session for a server."""

    id: str = field(default_factory=lambda: str(uuid4()))
    console_type: str = "novnc"  # novnc, spice, serial, etc.
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "console_type": self.console_type,
        }


@dataclass
class RemoteConsole:
    """Represents a remote console for server access."""

    type: str = "novnc"  # novnc, spice-html5, serial, etc.
    protocol: str = "vnc"  # vnc, spice, etc.
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "type": self.type,
            "protocol": self.protocol,
            "url": self.url,
        }


@dataclass
class ServerDiagnostics:
    """Represents server diagnostics information."""

    server_id: str = ""
    state: str = "running"
    driver: str = "libvirt"
    hypervisor: str = "kvm"
    hypervisor_os: str = "linux"
    uptime: int = 0
    config_drive: bool = False
    num_cpus: int = 1
    num_nics: int = 1
    num_disks: int = 1
    memory: int = 512  # MB
    cpu_details: list[dict[str, Any]] = field(default_factory=list)
    nic_details: list[dict[str, Any]] = field(default_factory=list)
    disk_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "state": self.state,
            "driver": self.driver,
            "hypervisor": self.hypervisor,
            "hypervisor_os": self.hypervisor_os,
            "uptime": self.uptime,
            "config_drive": self.config_drive,
            "num_cpus": self.num_cpus,
            "num_nics": self.num_nics,
            "num_disks": self.num_disks,
            "memory": self.memory,
            "cpu_details": self.cpu_details,
            "nic_details": self.nic_details,
            "disk_details": self.disk_details,
        }


@dataclass
class NovaExtension:
    """Represents a Nova API extension."""

    alias: str = ""
    name: str = ""
    namespace: str = ""
    description: str = ""
    updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "alias": self.alias,
            "name": self.name,
            "namespace": self.namespace,
            "description": self.description,
            "updated": self.updated,
            "links": [],
        }


# Neutron Extensions and Additional Models


@dataclass
class QosPolicy:
    """Represents a Neutron QoS policy."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    shared: bool = False
    is_default: bool = False
    project_id: str = ""
    rules: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "shared": self.shared,
            "is_default": self.is_default,
            "project_id": self.project_id,
            "tenant_id": self.project_id,  # Compatibility
            "rules": self.rules,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class QosRuleType:
    """Represents a QoS rule type."""

    type: str = ""  # bandwidth_limit, dscp_marking, minimum_bandwidth, etc.
    drivers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "type": self.type,
            "drivers": self.drivers,
        }


class AgentType(str, Enum):
    """Agent type enumeration."""

    DHCP_AGENT = "DHCP agent"
    L3_AGENT = "L3 agent"
    NEUTRON_METADATA_AGENT = "Metadata agent"
    NEUTRON_OPENVSWITCH_AGENT = "Open vSwitch agent"
    NEUTRON_LINUXBRIDGE_AGENT = "Linux bridge agent"


@dataclass
class NeutronAgent:
    """Represents a Neutron agent."""

    id: str = field(default_factory=lambda: str(uuid4()))
    agent_type: str = "Open vSwitch agent"
    binary: str = "neutron-openvswitch-agent"
    topic: str = "N/A"
    host: str = "neutron-host-1"
    availability_zone: str | None = None
    admin_state_up: bool = True
    alive: bool = True
    configurations: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime = field(default_factory=datetime.utcnow)
    heartbeat_timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "binary": self.binary,
            "topic": self.topic,
            "host": self.host,
            "availability_zone": self.availability_zone,
            "admin_state_up": self.admin_state_up,
            "alive": self.alive,
            "configurations": self.configurations,
            "created_at": format_datetime_utc(self.created_at),
            "started_at": format_datetime_utc(self.started_at),
            "heartbeat_timestamp": format_datetime_utc(self.heartbeat_timestamp),
        }


class TrunkStatus(str, Enum):
    """Trunk status enumeration."""

    ACTIVE = "ACTIVE"
    DOWN = "DOWN"
    BUILD = "BUILD"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass
class TrunkSubPort:
    """Represents a sub-port in a trunk."""

    port_id: str = ""
    segmentation_type: str = "vlan"  # vlan, inherit
    segmentation_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result: dict[str, Any] = {
            "port_id": self.port_id,
            "segmentation_type": self.segmentation_type,
        }
        if self.segmentation_id is not None:
            result["segmentation_id"] = self.segmentation_id
        return result


@dataclass
class Trunk:
    """Represents a Neutron trunk."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    port_id: str = ""  # Parent port
    status: TrunkStatus = TrunkStatus.ACTIVE
    admin_state_up: bool = True
    project_id: str = ""
    sub_ports: list[TrunkSubPort] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "port_id": self.port_id,
            "status": self.status.value,
            "admin_state_up": self.admin_state_up,
            "project_id": self.project_id,
            "tenant_id": self.project_id,  # Compatibility
            "sub_ports": [sp.to_dict() for sp in self.sub_ports],
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "tags": self.tags,
            "revision_number": 1,
        }


@dataclass
class NeutronExtension:
    """Represents a Neutron API extension."""

    alias: str = ""
    name: str = ""
    namespace: str = ""
    description: str = ""
    updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "alias": self.alias,
            "name": self.name,
            "namespace": self.namespace,
            "description": self.description,
            "updated": self.updated,
            "links": [],
        }


# Octavia Extensions and Additional Models


@dataclass
class OctaviaQuota:
    """Represents Octavia load balancer quotas for a project."""

    project_id: str = ""
    loadbalancer: int = 10
    listener: int = -1  # -1 means unlimited
    pool: int = 10
    member: int = 50
    healthmonitor: int = -1
    l7policy: int = 50
    l7rule: int = 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "loadbalancer": self.loadbalancer,
            "listener": self.listener,
            "pool": self.pool,
            "member": self.member,
            "healthmonitor": self.healthmonitor,
            "l7policy": self.l7policy,
            "l7rule": self.l7rule,
        }

    def to_detail_dict(self, usage: dict[str, int]) -> dict[str, Any]:
        """Convert to detailed quota response with usage."""
        return {
            "loadbalancer": {"limit": self.loadbalancer, "used": usage.get("loadbalancer", 0)},
            "listener": {"limit": self.listener, "used": usage.get("listener", 0)},
            "pool": {"limit": self.pool, "used": usage.get("pool", 0)},
            "member": {"limit": self.member, "used": usage.get("member", 0)},
            "healthmonitor": {"limit": self.healthmonitor, "used": usage.get("healthmonitor", 0)},
            "l7policy": {"limit": self.l7policy, "used": usage.get("l7policy", 0)},
            "l7rule": {"limit": self.l7rule, "used": usage.get("l7rule", 0)},
        }


@dataclass
class LoadBalancerFlavor:
    """Represents an Octavia load balancer flavor."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    enabled: bool = True
    flavor_profile_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "flavor_profile_id": self.flavor_profile_id,
        }


@dataclass
class LoadBalancerFlavorProfile:
    """Represents an Octavia flavor profile."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    provider_name: str = "amphora"
    flavor_data: str = "{}"  # JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "provider_name": self.provider_name,
            "flavor_data": self.flavor_data,
        }


@dataclass
class LoadBalancerAvailabilityZone:
    """Represents an Octavia availability zone."""

    name: str = ""
    description: str = ""
    enabled: bool = True
    availability_zone_profile_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "availability_zone_profile_id": self.availability_zone_profile_id,
        }


@dataclass
class LoadBalancerAvailabilityZoneProfile:
    """Represents an Octavia availability zone profile."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    provider_name: str = "amphora"
    availability_zone_data: str = "{}"  # JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "provider_name": self.provider_name,
            "availability_zone_data": self.availability_zone_data,
        }


@dataclass
class LoadBalancerProvider:
    """Represents an Octavia load balancer provider."""

    name: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "name": self.name,
            "description": self.description,
        }


# Cinder Extensions and Additional Models


class VolumeTransferStatus(str, Enum):
    """Volume transfer status enumeration."""

    CREATING = "creating"
    AVAILABLE = "available"
    DELETING = "deleting"
    ERROR = "error"
    ERROR_DELETING = "error_deleting"


@dataclass
class VolumeTransfer:
    """Represents a Cinder volume transfer."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    volume_id: str = ""
    auth_key: str = field(default_factory=lambda: str(uuid4()).replace("-", "")[:16])
    source_project_id: str = ""
    destination_project_id: str | None = None
    accepted: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "volume_id": self.volume_id,
            "auth_key": self.auth_key,
            "created_at": format_datetime_utc(self.created_at),
            "links": [
                {"rel": "self", "href": f"/v3/os-volume-transfer/{self.id}"},
            ],
        }


class BackupStatus(str, Enum):
    """Backup status enumeration."""

    CREATING = "creating"
    AVAILABLE = "available"
    DELETING = "deleting"
    ERROR = "error"
    ERROR_DELETING = "error_deleting"
    RESTORING = "restoring"


@dataclass
class VolumeBackup:
    """Represents a Cinder volume backup."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: BackupStatus = BackupStatus.CREATING
    volume_id: str = ""
    container: str = "volumebackups"
    size: int = 0  # GB (inherited from volume)
    object_count: int = 0
    availability_zone: str = "nova"
    project_id: str = ""
    user_id: str = ""
    is_incremental: bool = False
    has_dependent_backups: bool = False
    snapshot_id: str | None = None
    parent_id: str | None = None
    temp_volume_id: str | None = None
    temp_snapshot_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    data_timestamp: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "volume_id": self.volume_id,
            "container": self.container,
            "size": self.size,
            "object_count": self.object_count,
            "availability_zone": self.availability_zone,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "is_incremental": self.is_incremental,
            "has_dependent_backups": self.has_dependent_backups,
            "snapshot_id": self.snapshot_id,
            "parent_id": self.parent_id,
            "temp_volume_id": self.temp_volume_id,
            "temp_snapshot_id": self.temp_snapshot_id,
            "metadata": self.metadata,
            "data_timestamp": format_datetime_utc(self.data_timestamp),
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "links": [
                {"rel": "self", "href": f"/v3/backups/{self.id}"},
            ],
        }


class GroupStatus(str, Enum):
    """Consistency group status enumeration."""

    CREATING = "creating"
    AVAILABLE = "available"
    ERROR = "error"
    DELETING = "deleting"
    ERROR_DELETING = "error_deleting"
    UPDATING = "updating"


@dataclass
class ConsistencyGroup:
    """Represents a Cinder consistency group."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: GroupStatus = GroupStatus.CREATING
    availability_zone: str = "nova"
    group_type: str = ""
    group_snapshot_id: str | None = None
    source_group_id: str | None = None
    project_id: str = ""
    user_id: str = ""
    volume_types: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)  # volume IDs
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "availability_zone": self.availability_zone,
            "group_type": self.group_type,
            "group_snapshot_id": self.group_snapshot_id,
            "source_group_id": self.source_group_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "volume_types": self.volume_types,
            "volumes": self.volumes,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
        }


@dataclass
class GroupSnapshot:
    """Represents a Cinder group snapshot."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    status: GroupStatus = GroupStatus.CREATING
    group_id: str = ""
    group_type_id: str = ""
    project_id: str = ""
    user_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "group_id": self.group_id,
            "group_type_id": self.group_type_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
        }


# Glance Extensions and Additional Models


class TaskStatus(str, Enum):
    """Image task status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILURE = "failure"


class TaskType(str, Enum):
    """Image task type enumeration."""

    IMPORT = "import"
    EXPORT = "export"
    CLONE = "clone"


@dataclass
class ImageTask:
    """Represents a Glance image task."""

    id: str = field(default_factory=lambda: str(uuid4()))
    type: TaskType = TaskType.IMPORT
    status: TaskStatus = TaskStatus.PENDING
    owner: str = ""  # project_id
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result_dict = {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "owner": self.owner,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "input": self.input,
            "result": self.result,
            "message": self.message,
            "self": f"/v2/tasks/{self.id}",
            "schema": "/v2/schemas/task",
        }
        if self.expires_at:
            result_dict["expires_at"] = format_datetime_utc(self.expires_at)
        return result_dict


@dataclass
class MetadefNamespace:
    """Represents a Glance metadata definition namespace."""

    namespace: str = ""
    display_name: str = ""
    description: str = ""
    visibility: str = "private"  # public, private
    protected: bool = False
    owner: str = ""  # project_id
    properties: dict[str, Any] = field(default_factory=dict)
    objects: list[dict[str, Any]] = field(default_factory=list)
    resource_type_associations: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "namespace": self.namespace,
            "display_name": self.display_name,
            "description": self.description,
            "visibility": self.visibility,
            "protected": self.protected,
            "owner": self.owner,
            "properties": self.properties,
            "objects": self.objects,
            "resource_type_associations": self.resource_type_associations,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
            "self": f"/v2/metadefs/namespaces/{self.namespace}",
            "schema": "/v2/schemas/metadefs/namespace",
        }


@dataclass
class ImageCacheEntry:
    """Represents an image in the cache."""

    image_id: str = ""
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    last_modified: datetime = field(default_factory=datetime.utcnow)
    size: int = 0
    hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "image_id": self.image_id,
            "last_accessed": format_datetime_utc(self.last_accessed),
            "last_modified": format_datetime_utc(self.last_modified),
            "size": self.size,
            "hits": self.hits,
        }


@dataclass
class GlanceStore:
    """Represents a Glance store."""

    id: str = ""
    type: str = "file"  # file, swift, s3, etc.
    description: str = ""
    default: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "default": self.default,
        }


# Keystone Extensions and Additional Models


@dataclass
class ApplicationCredential:
    """Represents a Keystone application credential."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    user_id: str = ""
    project_id: str | None = None
    system: str | None = None
    expires_at: datetime | None = None
    roles: list[dict[str, str]] = field(default_factory=list)
    unrestricted: bool = False
    secret: str = field(default_factory=lambda: str(uuid4()).replace("-", ""))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        """Convert to API response format."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "system": self.system,
            "roles": self.roles,
            "unrestricted": self.unrestricted,
            "created_at": format_datetime_utc(self.created_at),
            "links": {"self": f"/v3/users/{self.user_id}/application_credentials/{self.id}"},
        }
        if self.expires_at:
            result["expires_at"] = format_datetime_utc(self.expires_at)
        if include_secret:
            result["secret"] = self.secret
        return result


@dataclass
class PolicyDocument:
    """Represents a Keystone policy document."""

    id: str = field(default_factory=lambda: str(uuid4()))
    blob: str = ""  # JSON policy document
    type: str = "application/json"
    user_id: str = ""
    project_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "blob": self.blob,
            "type": self.type,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "links": {"self": f"/v3/policies/{self.id}"},
        }


@dataclass
class IdentityProvider:
    """Represents a Keystone identity provider for federation."""

    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    enabled: bool = True
    remote_ids: list[str] = field(default_factory=list)
    domain_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "description": self.description,
            "enabled": self.enabled,
            "remote_ids": self.remote_ids,
            "domain_id": self.domain_id,
            "links": {"self": f"/v3/OS-FEDERATION/identity_providers/{self.id}"},
        }


@dataclass
class FederationProtocol:
    """Represents a federation protocol."""

    id: str = ""
    mapping_id: str = ""
    identity_provider_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "mapping_id": self.mapping_id,
            "links": {
                "self": f"/v3/OS-FEDERATION/identity_providers/{self.identity_provider_id}/protocols/{self.id}"
            },
        }


@dataclass
class FederationMapping:
    """Represents a federation mapping."""

    id: str = field(default_factory=lambda: str(uuid4()))
    rules: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "rules": self.rules,
            "links": {"self": f"/v3/OS-FEDERATION/mappings/{self.id}"},
        }


@dataclass
class RegisteredLimit:
    """Represents a Keystone registered limit."""

    id: str = field(default_factory=lambda: str(uuid4()))
    service_id: str = ""
    resource_name: str = ""
    default_limit: int = -1
    description: str = ""
    region_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        result = {
            "id": self.id,
            "service_id": self.service_id,
            "resource_name": self.resource_name,
            "default_limit": self.default_limit,
            "description": self.description,
            "links": {"self": f"/v3/registered_limits/{self.id}"},
        }
        if self.region_id:
            result["region_id"] = self.region_id
        return result


@dataclass
class NeutronFlavor:
    """Represents a Neutron service flavor."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    service_type: str = ""  # L3_ROUTER_NAT, LOADBALANCERV2, etc.
    enabled: bool = True
    service_profiles: list[str] = field(default_factory=list)  # service profile IDs
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "service_type": self.service_type,
            "enabled": self.enabled,
            "service_profiles": self.service_profiles,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
        }


@dataclass
class ServiceProfile:
    """Represents a Neutron service profile."""

    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    driver: str = ""
    enabled: bool = True
    metainfo: str = "{}"  # JSON string with driver-specific info
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "id": self.id,
            "description": self.description,
            "driver": self.driver,
            "enabled": self.enabled,
            "metainfo": self.metainfo,
            "created_at": format_datetime_utc(self.created_at),
            "updated_at": format_datetime_utc(self.updated_at),
        }
