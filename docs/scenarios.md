# Scenario/Failure Injection

The Scenario service allows you to simulate various failure conditions to test your OpenStack client's resilience.

## Overview

- **API URL**: http://localhost:8999/
- **Swagger UI**: http://localhost:8999/docs
- **Web UI**: Available in the Status UI "Scenarios" tab

## Built-in Scenarios

### Performance Scenarios

| Scenario | Description |
|----------|-------------|
| `light_load` | Light system load (100-500ms delays) |
| `system_under_load` | Moderate load (500-3000ms delays) |
| `heavy_load` | Heavy load with spikes |
| `system_stressed` | Severe load with timeouts |
| `gradual_degradation` | Increasing latency over time |

### Service Crash Scenarios

| Scenario | Description |
|----------|-------------|
| `nova_oom_crash` | Nova returns 503 errors |
| `glance_unavailable` | Glance returns 503 errors |

### Storage Scenarios

| Scenario | Description |
|----------|-------------|
| `cinder_disk_full` | Volume creation fails |
| `slow_storage_backend` | High latency storage operations |

### Network Scenarios

| Scenario | Description |
|----------|-------------|
| `neutron_network_partition` | Random network failures |

### Message Queue Scenarios

| Scenario | Description |
|----------|-------------|
| `rabbitmq_unstable` | Intermittent failures |
| `rabbitmq_down` | Complete MQ failure |

### Other Scenarios

| Scenario | Description |
|----------|-------------|
| `database_connection_lost` | Database connectivity failure |
| `quota_exceeded` | Create operations fail |
| `keystone_overloaded` | Auth rate limiting |

## API Endpoints

### List Scenarios

```bash
# List all available scenarios
curl http://localhost:8999/scenarios | jq

# Get active scenarios
curl http://localhost:8999/scenarios/active | jq
```

### Enable/Disable Scenarios

```bash
# Enable a scenario
curl -X POST http://localhost:8999/scenarios/heavy_load/enable | jq

# Disable a scenario
curl -X POST http://localhost:8999/scenarios/heavy_load/disable | jq

# Reset all scenarios
curl -X POST http://localhost:8999/scenarios/reset | jq
```

### Load Presets

```bash
# Apply a preset (light, moderate, heavy, stressed, chaos)
curl -X POST http://localhost:8999/scenarios/preset/heavy | jq

# Set load level (0-100%)
curl -X POST http://localhost:8999/scenarios/load \
  -H "Content-Type: application/json" \
  -d '{"level": 50}' | jq
```

### Statistics

```bash
# Get injection statistics
curl http://localhost:8999/scenarios/stats | jq
```

### Custom Scenarios

```bash
curl -X POST http://localhost:8999/scenarios/custom \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_scenario",
    "name": "My Custom Scenario",
    "description": "Custom test scenario",
    "category": "performance",
    "failureType": "slow_response",
    "loadProfile": {
      "minDelayMs": 500,
      "maxDelayMs": 2000
    }
  }' | jq
```

## Usage Examples

### Testing with Failure Injection

```bash
# Enable Nova crash scenario
curl -X POST http://localhost:8999/scenarios/nova_oom_crash/enable

# Now Nova API calls will fail with 503
curl -s http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN"
# Returns: {"error": {"message": "Service Unavailable...", "code": 503}}

# Disable the scenario
curl -X POST http://localhost:8999/scenarios/nova_oom_crash/disable
```

### Load Testing

```bash
# Set 50% load level (adds latency to all requests)
curl -X POST http://localhost:8999/scenarios/load \
  -H "Content-Type: application/json" \
  -d '{"level": 50}'

# API calls now have artificial delays
time curl -s http://localhost:8774/v2.1/flavors \
  -H "X-Auth-Token: $TOKEN"
# real    0m1.234s  (includes injected delay)

# Reset to normal
curl -X POST http://localhost:8999/scenarios/reset
```

## Cross-Process State Sharing

When running multiple services as separate processes, the Scenario service shares state via file:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Process Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Scenarios Service (8999)         Nova Service (8774)           │
│  ┌─────────────────────┐         ┌─────────────────────┐        │
│  │ POST /enable        │         │ ScenarioMiddleware  │        │
│  │       │             │         │       │             │        │
│  │       ▼             │         │       ▼             │        │
│  │  Write to file ─────┼─────────┼──► Read from file   │        │
│  └─────────────────────┘         └─────────────────────┘        │
│                                                                  │
│  State File: /tmp/openstack-emulator-scenarios.json             │
└─────────────────────────────────────────────────────────────────┘
```

- **State File**: `/tmp/openstack-emulator-scenarios.json`
- **File Locking**: Uses `fcntl` for safe concurrent access
- **Caching**: State cached with 0.5s TTL
- **Automatic Sync**: Middleware reads state before each request

## Related Documentation

- [Usage Guide](./usage.md) - General usage
- [API Examples](./api-examples.md) - API reference
