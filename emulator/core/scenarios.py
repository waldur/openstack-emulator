"""Scenario models for failure and load injection in OpenStack emulator."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    """Types of failures that can be injected."""

    SERVICE_UNAVAILABLE = "service_unavailable"  # 503 errors
    INTERMITTENT_FAILURE = "intermittent"  # Random failures
    SLOW_RESPONSE = "slow_response"  # Latency injection
    RESOURCE_EXHAUSTED = "resource_exhausted"  # OOM, disk full, quota
    PARTIAL_FAILURE = "partial_failure"  # Some operations fail
    DATA_CORRUPTION = "data_corruption"  # Invalid responses
    TIMEOUT = "timeout"  # Request timeouts (408/504)
    RATE_LIMITED = "rate_limited"  # 429 errors
    CONNECTION_ERROR = "connection_error"  # Simulates network issues


class ScenarioCategory(str, Enum):
    """Categories of scenarios for organization."""

    PERFORMANCE = "performance"  # Load and latency scenarios
    SERVICE_CRASH = "service_crash"  # Service unavailability
    STORAGE = "storage"  # Disk/volume related failures
    NETWORK = "network"  # Network partitions, connectivity
    MESSAGE_QUEUE = "message_queue"  # RabbitMQ/messaging failures
    DATABASE = "database"  # Database connectivity issues
    RESOURCE = "resource"  # Resource exhaustion (quota, memory)
    AUTHENTICATION = "authentication"  # Auth/token failures


class DelayDistribution(str, Enum):
    """Distribution types for delay calculation."""

    UNIFORM = "uniform"  # Even distribution between min and max
    NORMAL = "normal"  # Bell curve centered between min and max
    EXPONENTIAL = "exponential"  # Most requests fast, some very slow


@dataclass
class GradualDegradation:
    """Configuration for gradual performance degradation over time."""

    enabled: bool = False
    initial_delay_ms: int = 100
    increase_per_minute_ms: int = 200
    max_delay_ms: int = 30000
    started_at: datetime | None = None

    def get_current_delay_ms(self) -> int:
        """Calculate current delay based on elapsed time."""
        if not self.enabled or not self.started_at:
            return self.initial_delay_ms

        elapsed_minutes = (datetime.utcnow() - self.started_at).total_seconds() / 60
        current_delay = self.initial_delay_ms + int(elapsed_minutes * self.increase_per_minute_ms)
        return min(current_delay, self.max_delay_ms)


@dataclass
class LoadProfile:
    """Configuration for load/latency simulation."""

    min_delay_ms: int = 0
    max_delay_ms: int = 0
    distribution: DelayDistribution = DelayDistribution.UNIFORM
    spike_probability: float = 0.0  # 0.0-1.0, chance of extra delay
    spike_multiplier: float = 3.0  # How much worse spikes are
    timeout_probability: float = 0.0  # Chance of timeout (408/504)
    affected_operations: list[str] = field(
        default_factory=lambda: ["all"]
    )  # ["read", "write", "all"]
    gradual_degradation: GradualDegradation = field(default_factory=GradualDegradation)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "min_delay_ms": self.min_delay_ms,
            "max_delay_ms": self.max_delay_ms,
            "distribution": self.distribution.value,
            "spike_probability": self.spike_probability,
            "spike_multiplier": self.spike_multiplier,
            "timeout_probability": self.timeout_probability,
            "affected_operations": self.affected_operations,
            "gradual_degradation": {
                "enabled": self.gradual_degradation.enabled,
                "initial_delay_ms": self.gradual_degradation.initial_delay_ms,
                "increase_per_minute_ms": self.gradual_degradation.increase_per_minute_ms,
                "max_delay_ms": self.gradual_degradation.max_delay_ms,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoadProfile":
        """Create LoadProfile from dictionary."""
        gradual_data = data.get("gradual_degradation", {})
        return cls(
            min_delay_ms=data.get("min_delay_ms", 0),
            max_delay_ms=data.get("max_delay_ms", 0),
            distribution=DelayDistribution(data.get("distribution", "uniform")),
            spike_probability=data.get("spike_probability", 0.0),
            spike_multiplier=data.get("spike_multiplier", 3.0),
            timeout_probability=data.get("timeout_probability", 0.0),
            affected_operations=data.get("affected_operations", ["all"]),
            gradual_degradation=GradualDegradation(
                enabled=gradual_data.get("enabled", False),
                initial_delay_ms=gradual_data.get("initial_delay_ms", 100),
                increase_per_minute_ms=gradual_data.get("increase_per_minute_ms", 200),
                max_delay_ms=gradual_data.get("max_delay_ms", 30000),
            ),
        )


@dataclass
class FailureConfig:
    """Configuration for failure injection."""

    failure_probability: float = 1.0  # 0.0-1.0, chance of failure occurring
    error_message: str = ""  # Custom error message
    error_code: int = 500  # HTTP status code to return
    affected_operations: list[str] = field(
        default_factory=lambda: ["all"]
    )  # ["create", "read", "update", "delete", "all"]
    affected_resources: list[str] = field(
        default_factory=lambda: ["all"]
    )  # ["server", "volume", "network", "all"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "failure_probability": self.failure_probability,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "affected_operations": self.affected_operations,
            "affected_resources": self.affected_resources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureConfig":
        """Create FailureConfig from dictionary."""
        return cls(
            failure_probability=data.get("failure_probability", 1.0),
            error_message=data.get("error_message", ""),
            error_code=data.get("error_code", 500),
            affected_operations=data.get("affected_operations", ["all"]),
            affected_resources=data.get("affected_resources", ["all"]),
        )


@dataclass
class ScenarioStats:
    """Statistics for a scenario's injection activity."""

    times_triggered: int = 0
    total_delay_injected_ms: int = 0
    failures_injected: int = 0
    timeouts_injected: int = 0
    last_triggered: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "times_triggered": self.times_triggered,
            "total_delay_injected_ms": self.total_delay_injected_ms,
            "failures_injected": self.failures_injected,
            "timeouts_injected": self.timeouts_injected,
            "last_triggered": (self.last_triggered.isoformat() if self.last_triggered else None),
        }


@dataclass
class Scenario:
    """Definition of a failure/load scenario."""

    id: str
    name: str
    description: str
    category: ScenarioCategory
    failure_type: FailureType
    target_service: str | None = None  # None = all services
    load_profile: LoadProfile = field(default_factory=LoadProfile)
    failure_config: FailureConfig = field(default_factory=FailureConfig)
    enabled: bool = False
    enabled_at: datetime | None = None
    stats: ScenarioStats = field(default_factory=ScenarioStats)
    builtin: bool = True  # False for user-created scenarios

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "failure_type": self.failure_type.value,
            "target_service": self.target_service,
            "load_profile": self.load_profile.to_dict(),
            "failure_config": self.failure_config.to_dict(),
            "enabled": self.enabled,
            "enabled_at": self.enabled_at.isoformat() if self.enabled_at else None,
            "stats": self.stats.to_dict(),
            "builtin": self.builtin,
        }


# =============================================================================
# Built-in Scenario Definitions
# =============================================================================


def get_builtin_scenarios() -> list[Scenario]:
    """Return all built-in scenarios."""
    return [
        # Performance / Load scenarios
        Scenario(
            id="system_under_load",
            name="System Under Load",
            description="Simulates general system load - all requests respond slower",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=500,
                max_delay_ms=3000,
                distribution=DelayDistribution.NORMAL,
            ),
        ),
        Scenario(
            id="light_load",
            name="Light Load",
            description="Slight system slowdown, minimal impact",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=100,
                max_delay_ms=500,
                distribution=DelayDistribution.UNIFORM,
            ),
        ),
        Scenario(
            id="heavy_load",
            name="Heavy Load",
            description="Significant system slowdown, noticeable delays",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=5000,
                distribution=DelayDistribution.NORMAL,
                spike_probability=0.1,
                spike_multiplier=2.0,
            ),
        ),
        Scenario(
            id="system_stressed",
            name="System Stressed",
            description="Severe load with occasional timeouts",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=2000,
                max_delay_ms=10000,
                distribution=DelayDistribution.EXPONENTIAL,
                spike_probability=0.2,
                spike_multiplier=3.0,
                timeout_probability=0.1,
            ),
        ),
        Scenario(
            id="gradual_degradation",
            name="Gradual Degradation",
            description="System performance degrades over time (simulates memory leak)",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=100,
                max_delay_ms=100,
                gradual_degradation=GradualDegradation(
                    enabled=True,
                    initial_delay_ms=100,
                    increase_per_minute_ms=500,
                    max_delay_ms=30000,
                ),
            ),
        ),
        # Service crash scenarios
        Scenario(
            id="nova_oom_crash",
            name="Nova OOM Crash",
            description="Nova service crashed due to out-of-memory, servers stuck in BUILD",
            category=ScenarioCategory.SERVICE_CRASH,
            failure_type=FailureType.SERVICE_UNAVAILABLE,
            target_service="nova",
            failure_config=FailureConfig(
                error_message="Service Unavailable: Nova compute service not responding",
                error_code=503,
            ),
        ),
        Scenario(
            id="keystone_overloaded",
            name="Keystone Overloaded",
            description="Identity service is rate-limiting requests",
            category=ScenarioCategory.AUTHENTICATION,
            failure_type=FailureType.RATE_LIMITED,
            target_service="keystone",
            failure_config=FailureConfig(
                failure_probability=0.7,
                error_message="Rate limit exceeded. Please retry after 60 seconds.",
                error_code=429,
            ),
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=3000,
            ),
        ),
        Scenario(
            id="glance_unavailable",
            name="Glance Unavailable",
            description="Image service is down, image operations fail",
            category=ScenarioCategory.SERVICE_CRASH,
            failure_type=FailureType.SERVICE_UNAVAILABLE,
            target_service="glance",
            failure_config=FailureConfig(
                error_message="Image service unavailable",
                error_code=503,
            ),
        ),
        # Storage scenarios
        Scenario(
            id="cinder_disk_full",
            name="Cinder Disk Full",
            description="Storage backend has no space left, volume creation fails",
            category=ScenarioCategory.STORAGE,
            failure_type=FailureType.RESOURCE_EXHAUSTED,
            target_service="cinder",
            failure_config=FailureConfig(
                error_message="No space left on device. Volume creation failed.",
                error_code=413,
                affected_operations=["create"],
            ),
        ),
        Scenario(
            id="slow_storage_backend",
            name="Slow Storage Backend",
            description="Storage operations have high latency (overloaded SAN)",
            category=ScenarioCategory.STORAGE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service="cinder",
            load_profile=LoadProfile(
                min_delay_ms=5000,
                max_delay_ms=30000,
                distribution=DelayDistribution.EXPONENTIAL,
            ),
        ),
        # Network scenarios
        Scenario(
            id="neutron_network_partition",
            name="Neutron Network Partition",
            description="Network operations fail randomly (simulates network issues)",
            category=ScenarioCategory.NETWORK,
            failure_type=FailureType.INTERMITTENT_FAILURE,
            target_service="neutron",
            failure_config=FailureConfig(
                failure_probability=0.5,
                error_message="Network agent not responding",
                error_code=503,
            ),
        ),
        Scenario(
            id="neutron_slow",
            name="Neutron Slow",
            description="Network operations are slow (SDN controller overloaded)",
            category=ScenarioCategory.NETWORK,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service="neutron",
            load_profile=LoadProfile(
                min_delay_ms=2000,
                max_delay_ms=8000,
                distribution=DelayDistribution.NORMAL,
            ),
        ),
        # Message queue scenarios
        Scenario(
            id="rabbitmq_unstable",
            name="RabbitMQ Unstable",
            description="Message queue is unstable, async operations fail intermittently",
            category=ScenarioCategory.MESSAGE_QUEUE,
            failure_type=FailureType.INTERMITTENT_FAILURE,
            target_service=None,
            failure_config=FailureConfig(
                failure_probability=0.3,
                error_message="AMQP connection lost. Message delivery failed.",
                error_code=503,
                affected_operations=["create", "update", "delete"],
            ),
            load_profile=LoadProfile(
                min_delay_ms=500,
                max_delay_ms=2000,
            ),
        ),
        Scenario(
            id="rabbitmq_down",
            name="RabbitMQ Down",
            description="Message queue is completely unavailable",
            category=ScenarioCategory.MESSAGE_QUEUE,
            failure_type=FailureType.SERVICE_UNAVAILABLE,
            target_service=None,
            failure_config=FailureConfig(
                error_message="Cannot connect to message broker",
                error_code=503,
                affected_operations=["create", "update", "delete"],
            ),
        ),
        # Database scenarios
        Scenario(
            id="database_connection_lost",
            name="Database Connection Lost",
            description="Database connectivity issues, all operations fail",
            category=ScenarioCategory.DATABASE,
            failure_type=FailureType.CONNECTION_ERROR,
            target_service=None,
            failure_config=FailureConfig(
                error_message="Database connection failed: Connection refused",
                error_code=503,
            ),
        ),
        Scenario(
            id="database_slow",
            name="Database Slow",
            description="Database queries are slow (high load or replication lag)",
            category=ScenarioCategory.DATABASE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service=None,
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=5000,
                distribution=DelayDistribution.EXPONENTIAL,
            ),
        ),
        # Resource exhaustion scenarios
        Scenario(
            id="quota_exceeded",
            name="Quota Exceeded",
            description="Project quota exceeded, all create operations fail",
            category=ScenarioCategory.RESOURCE,
            failure_type=FailureType.RESOURCE_EXHAUSTED,
            target_service=None,
            failure_config=FailureConfig(
                error_message="Quota exceeded for project",
                error_code=413,
                affected_operations=["create"],
            ),
        ),
        # Per-service slow scenarios
        Scenario(
            id="nova_slow",
            name="Nova Slow",
            description="Compute service responding slowly",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service="nova",
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=5000,
                distribution=DelayDistribution.NORMAL,
            ),
        ),
        Scenario(
            id="cinder_slow",
            name="Cinder Slow",
            description="Block storage service responding slowly",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service="cinder",
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=5000,
                distribution=DelayDistribution.NORMAL,
            ),
        ),
        Scenario(
            id="glance_slow",
            name="Glance Slow",
            description="Image service responding slowly",
            category=ScenarioCategory.PERFORMANCE,
            failure_type=FailureType.SLOW_RESPONSE,
            target_service="glance",
            load_profile=LoadProfile(
                min_delay_ms=1000,
                max_delay_ms=5000,
                distribution=DelayDistribution.NORMAL,
            ),
        ),
        # Cascading failure
        Scenario(
            id="cascading_failure",
            name="Cascading Failure",
            description="Multiple services failing in cascade (simulates datacenter issues)",
            category=ScenarioCategory.SERVICE_CRASH,
            failure_type=FailureType.INTERMITTENT_FAILURE,
            target_service=None,
            failure_config=FailureConfig(
                failure_probability=0.6,
                error_message="Service temporarily unavailable due to upstream failure",
                error_code=503,
            ),
            load_profile=LoadProfile(
                min_delay_ms=2000,
                max_delay_ms=10000,
                spike_probability=0.3,
                timeout_probability=0.15,
            ),
        ),
    ]
