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

## How Injection Works

All services run in one process, so the Scenarios API, the Status UI and the
injection middleware share a single in-memory `scenario_manager`. Enabling a
scenario takes effect on the very next request — there is no synchronisation
step and no state file.

```
┌─────────────────────────────────────────────────────────────────┐
│  Scenarios API (8999)  ──┐                                       │
│  Status UI (10000)     ──┤                                       │
│                          ▼                                       │
│                  scenario_manager  ◄─── ScenarioMiddleware       │
│                   (in memory)            on every service app    │
└─────────────────────────────────────────────────────────────────┘
```

Per request the middleware derives an operation from the HTTP method
(`GET` → `read`, `POST` → `create`, …) and a resource from the path
(`/servers` → `server`), then asks the manager whether this service, operation
and resource should fail or be delayed. Scenarios only affect their
`target_service`, so enabling a Nova scenario leaves Neutron alone.

Injected responses are identifiable:

- `X-Scenario-Injection` — the scenario id that fired
- `X-Failure-Type` — e.g. `service_unavailable`
- `X-Timeout-Injected: true` — on an injected 504

`/health` and `/healthcheck` are never injected into, so probes stay green while
a scenario is active.

> **Note**: earlier versions synchronised this state through
> `/tmp/openstack-emulator-scenarios.json` for a multi-process layout that no
> longer exists. That file is gone; nothing reads or writes it.

## Related Documentation

- [Usage Guide](./usage.md) - General usage
- [API Examples](./api-examples.md) - API reference
