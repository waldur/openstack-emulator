# Architecture Overview

This document describes the architecture of the OpenStack Emulator.

## System Architecture

The OpenStack Emulator is a lightweight implementation of OpenStack APIs designed for testing purposes. It provides a simplified but API-compatible interface to core OpenStack services.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OpenStack Emulator                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Keystone   │  │    Nova     │  │   Cinder    │  │   Glance    │        │
│  │   (5000)    │  │   (8774)    │  │   (8776)    │  │   (9292)    │        │
│  │  Identity   │  │  Compute    │  │   Block     │  │   Image     │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Neutron   │  │   Octavia   │  │  Placement  │  │    Swift    │        │
│  │   (9696)    │  │   (9876)    │  │   (8778)    │  │   (8080)    │        │
│  │  Network    │  │  Load Bal.  │  │  Capacity   │  │   Object    │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ CloudKitty  │  │    OIDC     │  │   Status    │  │  Scenarios  │        │
│  │   (8889)    │  │   (5556)    │  │  (10000)    │  │   (8999)    │        │
│  │   Rating    │  │  OpenID P.  │  │   Web UI    │  │  Injection  │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                        │
│                          ┌─────────┴─────────┐                              │
│                          │   In-Memory DB    │                              │
│                          │    (Singleton)    │                              │
│                          └───────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Overview

### Core Services

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity and authentication service |
| Nova | 8774 | Compute service for virtual machine management |
| Cinder | 8776 | Block storage service for volumes |
| Glance | 9292 | Image service for VM images |
| Neutron | 9696 | Networking service |
| Octavia | 9876 | Load balancer service |
| Placement | 8778 | Resource provider / capacity tracking service |
| Swift | 8080 | Object storage service |
| OIDC | 5556 | Embedded OpenID Provider, for federation tests |
| CloudKitty | 8889 | Rating service |

### Management Services

| Service | Port | Description |
|---------|------|-------------|
| Status UI | 10000 | Web-based dashboard for monitoring and management |
| Scenarios | 8999 | Failure injection and load simulation API |

## Technology Stack

- **Framework**: FastAPI (async REST API framework)
- **Validation**: Pydantic (request/response validation)
- **Database**: In-memory Python dictionaries (thread-safe)
- **Concurrency**: One process; every service app runs as an asyncio task on its own port

## Key Design Decisions

### 1. In-Memory Database

The emulator uses an in-memory database implemented as Python dictionaries within a singleton `Database` class. This provides:

- Zero external dependencies
- Fast read/write operations
- Simple reset capability for testing
- Thread-safe access via `threading.RLock`

**Trade-off**: Data lives only in memory unless `--persist-db <path>` is given, in
which case the whole database is written to a single JSON file (on every change
with `--auto-save`, otherwise on demand) and restored at startup. Serialization
is derived from the model dataclasses — see
[`emulator/core/persistence.py`](../../emulator/core/persistence.py) and
[Development](../development.md#persistence).

### 2. One Port Per Service, One Process

Each OpenStack service is a separate FastAPI app listening on its own standard
port, so clients discover and address them exactly as they would a real
deployment. All of them run as asyncio tasks inside a single process
(`run_all_services_async` in
[`emulator/api/unified_app.py`](../../emulator/api/unified_app.py)), which is
what lets them share one in-memory database without any IPC. This:

- Mimics real OpenStack deployment topology from the client's side
- Enables realistic service discovery testing
- Means services cannot be restarted or scaled independently

Because the services share a process and therefore one stdout, each request is
logged by an access-log middleware that names the service and port that handled
it; uvicorn's own access log cannot distinguish them.

### 3. Simplified Authentication, Real Authorization

Passwords are not checked — any username authenticates, and an unknown name
becomes a stable identity derived from the name and domain rather than the
seeded admin. Authorization is not simplified in the same way:

- Scoping a token to a project requires a real role assignment on it. Without
  one, `POST /v3/auth/tokens` fails the way Keystone's `_validate_project_scope`
  fails, instead of quietly returning a usable token.
- A rejected token is answered with `401`, not `404`.
- Privilege comes from holding the `admin` role (or scoping to the `admin`
  project); a privileged token may address resources across projects, while a
  tenant-scoped token stays isolated. See
  [`emulator/core/simple_auth.py`](../../emulator/core/simple_auth.py).

Federated authentication is supported end to end — an OIDC token from the
embedded provider maps to a Keystone user via an identity provider, protocol
and mapping. See [Federation](../federation.md).

### 4. Immediate Resource Transitions

Unlike real OpenStack where resource creation is asynchronous (BUILD -> ACTIVE), the emulator transitions resources immediately. This simplifies testing but can be extended for async behavior testing.

## Directory Structure

```
emulator/
├── __init__.py          # CLI entry point (argument parsing, service startup)
├── api/                 # REST API layer
│   ├── unified_app.py   # Builds every service app; runs them as asyncio tasks
│   ├── keystone.py      # Keystone API routes
│   ├── nova.py          # Nova API routes
│   ├── cinder.py        # Cinder API routes
│   ├── glance.py        # Glance API routes
│   ├── neutron.py       # Neutron API routes
│   ├── octavia.py       # Octavia API routes
│   ├── placement.py     # Placement API routes
│   ├── swift.py         # Swift object storage routes
│   ├── oidc.py          # Embedded OpenID Provider routes
│   ├── cloudkitty.py    # CloudKitty rating routes
│   ├── presets.py       # Preset loading
│   ├── scenarios.py     # Scenario injection routes
│   └── status_ui.py     # Status Web UI routes
├── core/                # Core business logic
│   ├── database.py      # In-memory database
│   ├── models.py        # Data models (dataclasses)
│   ├── persistence.py   # Dataclass-derived JSON save/load
│   ├── federation.py    # Federated identity mapping
│   ├── simple_auth.py   # Token validation shared by every service
│   ├── exceptions.py    # Domain errors (e.g. unauthorized scope)
│   ├── headers.py       # Header helpers
│   ├── middleware.py    # Scenario injection middleware
│   ├── logging_middleware.py  # Per-service access log
│   ├── scenarios.py     # Scenario definitions
│   └── scenario_manager.py  # Scenario state (shared by the API, UI and middleware)
└── presets/             # Built-in preset YAMLs (development, production, …)
```

## Related Documentation

- [Data Models](./data-models.md) - Detailed data model documentation
- [Tenant Isolation](./tenant-isolation.md) - Multi-tenancy and resource isolation
