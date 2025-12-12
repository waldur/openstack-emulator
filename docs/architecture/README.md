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

**Trade-off**: Data is not persisted across restarts.

### 2. Multi-Process Architecture

Each OpenStack service runs as a separate process on its standard port. This:

- Mimics real OpenStack deployment topology
- Allows independent scaling/restart of services
- Enables realistic service discovery testing

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
│   ├── scenarios.py     # Scenario injection routes
│   └── status_ui.py     # Status Web UI routes
└── core/                # Core business logic
    ├── database.py      # In-memory database
    ├── models.py        # Data models (dataclasses)
    ├── middleware.py    # Scenario injection middleware
    ├── scenarios.py     # Scenario definitions
    ├── scenario_manager.py  # Scenario state management
    └── shared_state.py  # Cross-process state sharing
```

## Related Documentation

- [Data Models](./data-models.md) - Detailed data model documentation
- [Tenant Isolation](./tenant-isolation.md) - Multi-tenancy and resource isolation
