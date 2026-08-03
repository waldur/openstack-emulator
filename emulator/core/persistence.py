"""Generic dataclass <-> JSON codec and the registry of persisted state.

The emulator keeps everything in memory as dataclasses. Persistence used to be
hand-written ``_x_to_dict``/``_dict_to_x`` pairs, one per model, which drifted
from the models they mirrored: fields were quietly dropped, whole collections
were never written, and enum fields came back as plain strings so ``to_dict()``
raised ``AttributeError: 'str' object has no attribute 'value'`` on the first
list call after a restart.

Both directions here are driven by the dataclass annotations instead. A field
round-trips because its declared type says how, not because someone remembered
to add it to two functions. Adding a field to a model is enough; adding a new
collection to :class:`~emulator.core.database.Database` requires an entry in
:data:`PERSISTED` or :data:`NOT_PERSISTED`, which ``tests/test_persistence.py``
enforces.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from datetime import datetime
from typing import Any

from emulator.core.models import (
    ApplicationCredential,
    CinderQuota,
    ConsistencyGroup,
    Credential,
    Domain,
    Endpoint,
    FederationMapping,
    FederationProtocol,
    Flavor,
    FloatingIP,
    GlanceImage,
    Group,
    GroupSnapshot,
    HealthMonitor,
    IdentityProvider,
    Image,
    ImageCacheEntry,
    ImageMember,
    ImageTask,
    Keypair,
    L7Policy,
    L7Rule,
    Listener,
    LoadBalancer,
    LoadBalancerAvailabilityZone,
    LoadBalancerAvailabilityZoneProfile,
    LoadBalancerFlavor,
    LoadBalancerFlavorProfile,
    MetadefNamespace,
    Network,
    NeutronAgent,
    NeutronFlavor,
    NeutronQuota,
    NovaQuota,
    OctaviaQuota,
    OidcClient,
    OidcUser,
    PolicyDocument,
    Pool,
    PoolMember,
    Port,
    Project,
    QosPolicy,
    QosSpec,
    RbacPolicy,
    Region,
    RegisteredLimit,
    ResourceProvider,
    Role,
    RoleAssignment,
    Router,
    SecurityGroup,
    SecurityGroupRule,
    Server,
    ServerConsole,
    ServerGroup,
    ServerNetworkInterface,
    ServerVolumeAttachment,
    Service,
    ServiceProfile,
    ServiceProvider,
    Snapshot,
    Subnet,
    SwiftAccount,
    SwiftContainer,
    SwiftObject,
    Trunk,
    User,
    Volume,
    VolumeBackup,
    VolumeTransfer,
    VolumeType,
)

#: Bumped when the on-disk layout changes incompatibly. Files written before
#: versioning (no ``schema_version`` key) are read by the legacy reader in
#: ``Database._load_legacy_v1`` and rewritten in the current format on the next
#: save.
SCHEMA_VERSION = 2


# --------------------------------------------------------------------------
# Codec
# --------------------------------------------------------------------------

_HINTS: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    """Resolved type hints for a dataclass, cached.

    ``get_type_hints`` resolves the string annotations produced by
    ``from __future__ import annotations`` and PEP 604 unions, which is what
    lets :func:`decode` know that ``status`` is a ``NetworkStatus`` and not a
    ``str``.
    """
    if cls not in _HINTS:
        _HINTS[cls] = typing.get_type_hints(cls)
    return _HINTS[cls]


def encode(value: Any) -> Any:
    """Convert an in-memory value to something ``json.dump`` accepts.

    Dispatches on the runtime type, so it needs no annotations. Raises
    ``TypeError`` for anything it does not understand rather than coercing it
    to a string: a silent ``str()`` fallback is what allowed the original
    round-trip bug to reach disk unnoticed.
    """
    # Enums first: the status enums subclass ``str``, so an isinstance check
    # against the primitives below would match them and write "ACTIVE" for
    # some and "NetworkStatus.ACTIVE" for others depending on the base class.
    if isinstance(value, enum.Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, (set, frozenset)):
        # Sorted so the file is stable across runs and diffable.
        return sorted(encode(v) for v in value)
    raise TypeError(f"Cannot serialize {type(value).__name__} for persistence")


def decode(annotation: Any, value: Any) -> Any:
    """Rebuild a value of the declared type from its JSON form."""
    if value is None:
        return None

    origin = typing.get_origin(annotation)

    args = typing.get_args(annotation)

    if origin in (types.UnionType, typing.Union):
        members = [a for a in args if a is not type(None)]
        # ``X | None`` is the only union shape the models use; anything wider
        # is ambiguous, so pass it through untouched.
        return decode(members[0], value) if len(members) == 1 else value

    if origin is list:
        return [decode(args[0] if args else Any, item) for item in value]

    if origin is set or origin is frozenset:
        return {decode(args[0] if args else Any, item) for item in value}

    if origin is dict:
        value_type = args[1] if len(args) == 2 else Any
        return {key: decode(value_type, item) for key, item in value.items()}

    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return annotation(value)
        if annotation is datetime:
            return datetime.fromisoformat(value)
        if dataclasses.is_dataclass(annotation):
            return decode_dataclass(annotation, value)

    return value


def decode_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Build a dataclass instance from a decoded mapping.

    Keys absent from ``data`` fall back to the field default, so a file written
    by an older build still loads. Keys the model no longer has are ignored, so
    a file written by a newer build loads too.
    """
    hints = _hints(cls)
    kwargs = {
        field.name: decode(hints.get(field.name, Any), data[field.name])
        for field in dataclasses.fields(cls)
        if field.init and field.name in data
    }
    return cls(**kwargs)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


class Shape(enum.Enum):
    """How a ``Database`` attribute is laid out."""

    DICT = "dict"  # dict[str, Model]
    LIST = "list"  # list[Model]
    DICT_OF_LIST = "dict_of_list"  # dict[str, list[Model]]
    DICT_OF_STR_SET = "dict_of_str_set"  # dict[str, set[str]]
    DICT_OF_STR = "dict_of_str"  # dict[str, str]
    DATACLASS = "dataclass"  # a single model instance


@dataclasses.dataclass(frozen=True)
class Collection:
    """One persisted attribute of :class:`~emulator.core.database.Database`."""

    key: str  # name used in the JSON file
    attr: str  # attribute name on Database
    shape: Shape
    model: type | None = None  # None for shapes that hold no dataclass


def _c(attr: str, model: type | None = None, shape: Shape = Shape.DICT) -> Collection:
    return Collection(key=attr.lstrip("_"), attr=attr, shape=shape, model=model)


#: Everything written to disk. Order matters only for readability of the file.
PERSISTED: tuple[Collection, ...] = (
    # Nova
    _c("_servers", Server),
    _c("_flavors", Flavor),
    _c("_images", Image),
    _c("_keypairs", Keypair),
    _c("_server_groups", ServerGroup),
    _c("_nova_quotas", NovaQuota),
    _c("_nova_quota_classes", NovaQuota),
    _c("_server_volume_attachments", ServerVolumeAttachment, Shape.DICT_OF_LIST),
    _c("_server_network_interfaces", ServerNetworkInterface, Shape.DICT_OF_LIST),
    _c("_server_consoles", ServerConsole, Shape.DICT_OF_LIST),
    _c("_server_tags", None, Shape.DICT_OF_STR_SET),
    # Keystone
    _c("_domains", Domain),
    _c("_projects", Project),
    _c("_users", User),
    _c("_roles", Role),
    _c("_role_assignments", RoleAssignment, Shape.LIST),
    _c("_groups", Group),
    _c("_group_memberships", None, Shape.DICT_OF_STR_SET),
    _c("_services", Service),
    _c("_service_ids", None, Shape.DICT_OF_STR),
    _c("_endpoints", Endpoint),
    _c("_regions", Region),
    _c("_credentials", Credential),
    _c("_application_credentials", ApplicationCredential),
    _c("_policy_documents", PolicyDocument),
    _c("_identity_providers", IdentityProvider),
    _c("_federation_protocols", FederationProtocol),
    _c("_federation_mappings", FederationMapping),
    _c("_service_providers", ServiceProvider),
    _c("_registered_limits", RegisteredLimit),
    # Cinder
    _c("_volumes", Volume),
    _c("_snapshots", Snapshot),
    _c("_volume_types", VolumeType),
    _c("_qos_specs", QosSpec),
    _c("_cinder_quotas", CinderQuota),
    _c("_cinder_quota_classes", CinderQuota),
    # OpenID Provider. Authorization codes are session state and deliberately
    # transient, like tokens.
    _c("_oidc_clients", OidcClient),
    _c("_oidc_users", OidcUser),
    # Swift
    _c("_swift_accounts", SwiftAccount),
    _c("_swift_containers", SwiftContainer),
    _c("_swift_objects", SwiftObject),
    _c("_volume_transfers", VolumeTransfer),
    _c("_volume_backups", VolumeBackup),
    _c("_consistency_groups", ConsistencyGroup),
    _c("_group_snapshots", GroupSnapshot),
    # Glance
    _c("_glance_images", GlanceImage),
    _c("_image_members", ImageMember, Shape.DICT_OF_LIST),
    _c("_image_tasks", ImageTask),
    _c("_metadef_namespaces", MetadefNamespace),
    _c("_image_cache", ImageCacheEntry),
    # Neutron
    _c("_networks", Network),
    _c("_subnets", Subnet),
    _c("_ports", Port),
    _c("_routers", Router),
    _c("_floating_ips", FloatingIP),
    _c("_security_groups", SecurityGroup),
    _c("_security_group_rules", SecurityGroupRule),
    _c("_neutron_quotas", NeutronQuota),
    _c("_rbac_policies", RbacPolicy),
    _c("_qos_policies", QosPolicy),
    _c("_neutron_agents", NeutronAgent),
    _c("_trunks", Trunk),
    _c("_neutron_flavors", NeutronFlavor),
    _c("_service_profiles", ServiceProfile),
    # Octavia
    _c("_load_balancers", LoadBalancer),
    _c("_listeners", Listener),
    _c("_pools", Pool),
    _c("_pool_members", PoolMember),
    _c("_health_monitors", HealthMonitor),
    _c("_l7policies", L7Policy),
    _c("_l7rules", L7Rule),
    _c("_octavia_quotas", OctaviaQuota),
    _c("_lb_flavors", LoadBalancerFlavor),
    _c("_lb_flavor_profiles", LoadBalancerFlavorProfile),
    _c("_lb_availability_zones", LoadBalancerAvailabilityZone),
    _c("_lb_availability_zone_profiles", LoadBalancerAvailabilityZoneProfile),
    # Placement
    _c("_resource_providers", ResourceProvider),
    # Singletons
    _c("_default_domain", Domain, Shape.DATACLASS),
)

#: Plain values that must survive a restart. The ID scalars are minted fresh by
#: ``_init_default_keystone_data`` on every boot while ``_projects``/``_users``/
#: ``_roles`` are replaced by the loaded ones, so without these the defaults
#: point at objects that no longer exist.
PERSISTED_SCALARS: tuple[str, ...] = (
    "_next_lb_vip",
    "_default_project_id",
    "_default_project_name",
    "_default_user_id",
    "_default_user_name",
)

#: Deliberately not written, with the reason. The coverage test requires every
#: ``Database`` attribute to appear here or in ``PERSISTED``/``PERSISTED_SCALARS``,
#: so a new collection cannot be added without making this choice.
NOT_PERSISTED: dict[str, str] = {
    "_oidc_codes": "short-lived authorization codes; session state",
    "_lock": "threading primitive",
    "_load_degraded": "bookkeeping for the current process",
    "_backup_done": "bookkeeping for the current process",
    "_tokens": "session state; tokens expire in 24h and are re-issued on demand",
    "_nova_extensions": "static capability list, must track the code not the file",
    "_neutron_extensions": "static capability list, must track the code not the file",
    "_qos_rule_types": "static catalogue seeded at boot",
    "_glance_stores": "static catalogue seeded at boot",
    "_lb_providers": "static catalogue seeded at boot",
}


# --------------------------------------------------------------------------
# Collection-level encode/decode
# --------------------------------------------------------------------------


def encode_collection(collection: Collection, value: Any) -> tuple[Any, list[str]]:
    """Serialize one whole collection, skipping records that fail.

    Mirrors :func:`decode_collection`. ``encode`` deliberately raises on a type
    it does not understand rather than stringifying it, which is what let the
    original round-trip bug reach disk — but a single off-type value must not
    cost every other record, and must not stop the file being written at all.
    Returns the encoded collection plus one description per dropped record.
    """
    if collection.shape is Shape.DICT_OF_STR_SET:
        return {key: sorted(items) for key, items in value.items()}, []

    dropped: list[str] = []

    if collection.shape is Shape.DICT:
        encoded: dict[str, Any] = {}
        for key, record in value.items():
            try:
                encoded[key] = encode(record)
            except Exception as e:
                dropped.append(f"{key}: {e}")
        return encoded, dropped

    if collection.shape is Shape.LIST:
        items = []
        for index, record in enumerate(value):
            try:
                items.append(encode(record))
            except Exception as e:
                dropped.append(f"[{index}]: {e}")
        return items, dropped

    if collection.shape is Shape.DICT_OF_LIST:
        grouped: dict[str, list[Any]] = {}
        for key, records in value.items():
            bucket = []
            for index, record in enumerate(records):
                try:
                    bucket.append(encode(record))
                except Exception as e:
                    dropped.append(f"{key}[{index}]: {e}")
            grouped[key] = bucket
        return grouped, dropped

    # DICT_OF_STR and DATACLASS are single small values with nothing to isolate.
    return encode(value), []


def decode_collection(collection: Collection, data: Any) -> tuple[Any, list[str]]:
    """Deserialize one whole collection, skipping records that fail.

    Returns the rebuilt collection plus one ``"<id>: <error>"`` string per
    dropped record, so the caller can say exactly what was lost. A malformed
    record must not take the rest of the file with it, but a bare count leaves
    nobody able to work out which record to repair.
    """
    model = collection.model

    if collection.shape is Shape.DICT_OF_STR_SET:
        return {key: set(items) for key, items in data.items()}, []
    if collection.shape is Shape.DICT_OF_STR:
        return dict(data), []
    if collection.shape is Shape.DATACLASS:
        assert model is not None
        return decode_dataclass(model, data), []

    assert model is not None
    dropped: list[str] = []

    if collection.shape is Shape.LIST:
        items = []
        for index, record in enumerate(data):
            try:
                items.append(decode_dataclass(model, record))
            except Exception as e:
                dropped.append(f"[{index}]: {e}")
        return items, dropped

    if collection.shape is Shape.DICT_OF_LIST:
        grouped: dict[str, list[Any]] = {}
        for key, records in data.items():
            bucket = []
            for index, record in enumerate(records):
                try:
                    bucket.append(decode_dataclass(model, record))
                except Exception as e:
                    dropped.append(f"{key}[{index}]: {e}")
            grouped[key] = bucket
        return grouped, dropped

    mapping: dict[str, Any] = {}
    for key, record in data.items():
        try:
            mapping[key] = decode_dataclass(model, record)
        except Exception as e:
            dropped.append(f"{key}: {e}")
    return mapping, dropped
