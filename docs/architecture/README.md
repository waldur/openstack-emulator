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
│  │   Neutron   │  │   Octavia   │  │   Status    │  │  Scenarios  │        │
│  │   (9696)    │  │   (9876)    │  │  (10000)    │  │   (8999)    │        │
│  │  Network    │  │  Load Bal.  │  │   Web UI    │  │  Injection  │        │
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

### Management Services

| Service | Port | Description |
|---------|------|-------------|
| Status UI | 10000 | Web-based dashboard for monitoring and management |
| Scenarios | 8999 | Failure injection and load simulation API |

## Technology Stack

- **Framework**: FastAPI (async REST API framework)
- **Validation**: Pydantic (request/response validation)
- **Database**: In-memory Python dictionaries (thread-safe)
- **Concurrency**: Multiprocessing (each service runs independently)

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

### 3. Simplified Authentication

While the emulator implements Keystone token authentication, it accepts any valid credentials by default. This simplifies testing while maintaining API compatibility.

### 4. Immediate Resource Transitions

Unlike real OpenStack where resource creation is asynchronous (BUILD -> ACTIVE), the emulator transitions resources immediately. This simplifies testing but can be extended for async behavior testing.

## Directory Structure

```
emulator/
├── __init__.py          # CLI entry point
├── api/                 # REST API layer
│   ├── app_*.py         # Standalone service applications
│   ├── keystone.py      # Keystone API routes
│   ├── nova.py          # Nova API routes
│   ├── cinder.py        # Cinder API routes
│   ├── glance.py        # Glance API routes
│   ├── neutron.py       # Neutron API routes
│   ├── octavia.py       # Octavia API routes
│   ├── placement.py     # Placement API routes
│   ├── scenarios.py     # Scenario injection routes
│   └── status_ui.py     # Status Web UI routes
└── core/                # Core business logic
    ├── database.py      # In-memory database
    ├── models.py        # Data models (dataclasses)
    ├── middleware.py    # Scenario injection middleware
    ├── scenarios.py     # Scenario definitions
    └── scenario_manager.py  # Scenario state (shared by the API, UI and middleware)
```

## Related Documentation

- [Data Models](./data-models.md) - Detailed data model documentation
- [Tenant Isolation](./tenant-isolation.md) - Multi-tenancy and resource isolation
