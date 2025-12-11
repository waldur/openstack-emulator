# OpenStack Emulator - Development Guide

This file contains instructions for developing and extending the OpenStack emulator.

## Project Overview

This is a lightweight OpenStack API emulator for testing purposes. It provides simplified implementations of OpenStack services that can be used to develop and test OpenStack clients without a full OpenStack deployment.

## Architecture

- **FastAPI**: REST API framework
- **Pydantic**: Request/response validation
- **In-memory database**: No external dependencies
- **Multiprocessing**: Each service runs on its own port

## Standard OpenStack Service Ports

When adding new services, use the standard OpenStack ports:

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity service |
| Nova | 8774 | Compute service |
| Cinder | 8776 | Block Storage service |
| Glance | 9292 | Image service |
| Neutron | 9696 | Networking service |
| Swift | 8080 | Object Storage service |
| Heat | 8004 | Orchestration service |
| Placement | 8778 | Placement service |
| Barbican | 9311 | Key Manager service |
| Octavia | 9876 | Load Balancer service |
| Manila | 8786 | Shared File Systems service |
| Ironic | 6385 | Bare Metal service |
| Designate | 9001 | DNS service |
| Trove | 8779 | Database service |
| Magnum | 9511 | Container Infrastructure Management |
| Sahara | 8386 | Data Processing service |

Reference: https://docs.openstack.org/install-guide/firewalls-default-ports.html

## Adding a New Service

Follow these steps to add a new OpenStack service:

### 1. Add Models (emulator/core/models.py)

Add dataclasses for the service's resources:

```python
from dataclasses import dataclass, field
from enum import Enum

class ResourceStatus(Enum):
    ACTIVE = "active"
    CREATING = "creating"
    ERROR = "error"

@dataclass
class Resource:
    id: str
    name: str
    status: ResourceStatus = ResourceStatus.ACTIVE
    created_at: str = ""
    updated_at: str = ""
```

### 2. Add Database Operations (emulator/core/database.py)

Add storage and CRUD operations:

```python
# In Database.__init__:
self.resources: dict[str, Resource] = {}

# Add methods:
def create_resource(self, resource: Resource) -> Resource:
    self.resources[resource.id] = resource
    return resource

def get_resource(self, resource_id: str) -> Resource | None:
    return self.resources.get(resource_id)

def list_resources(self) -> list[Resource]:
    return list(self.resources.values())

def delete_resource(self, resource_id: str) -> bool:
    if resource_id in self.resources:
        del self.resources[resource_id]
        return True
    return False
```

Update `_generate_service_catalog()` to include the new service endpoint.

### 3. Create API Routes (emulator/api/<service>.py)

Create a new file with FastAPI routes:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

router = APIRouter()

class ResourceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str

@router.get("/v2/resources")
async def list_resources():
    # Implementation
    pass

@router.post("/v2/resources")
async def create_resource(request: ResourceRequest):
    # Implementation
    pass
```

### 4. Create Standalone App (emulator/api/app_<service>.py)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from emulator.api.<service> import router

app = FastAPI(
    title="OpenStack <Service> Emulator",
    description="A lightweight OpenStack <Service> API emulator",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "<service>"}
```

### 5. Register Service (emulator/__init__.py)

Add the service to the CLI:

```python
SERVICE_PORTS = {
    # ... existing services
    "<service>": <port>,  # Use standard OpenStack port
}

SERVICE_APPS = {
    # ... existing services
    "<service>": "emulator.api.app_<service>:app",
}
```

### 6. Update Service Catalog (emulator/core/database.py)

In `_generate_service_catalog()`, add the new service:

```python
service_url = f"{scheme}://{host}:<port>"
# Add to catalog list
```

### 7. Add Tests (tests/test_<service>.py)

Create comprehensive tests:

```python
import pytest
from fastapi.testclient import TestClient
from emulator.api.app_<service> import app

client = TestClient(app)

def test_list_resources():
    response = client.get("/v2/resources")
    assert response.status_code == 200

def test_create_resource():
    response = client.post("/v2/resources", json={"name": "test"})
    assert response.status_code == 201
```

### 8. Update Documentation (README.md)

Add documentation for the new service including:
- Feature list
- API examples
- Port information

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run tests with coverage
pytest --cov=emulator --cov-report=html

# Run specific service tests
pytest tests/test_<service>.py -v
```

## Code Style

- Use type hints for all functions
- Use Pydantic `ConfigDict` instead of nested `Config` class
- Use `response_model=None` for routes returning `Response` objects
- Follow OpenStack API patterns for request/response formats

## Pre-commit Requirements

**IMPORTANT: You MUST run the black linter and ensure it passes before committing any code.**

### Black Linter

All Python code must be formatted with black before committing. This is a strict requirement - commits with unformatted code are not acceptable.

```bash
# Check if code passes black formatting (dry run)
black --check .

# Format all Python files
black .

# Format specific files
black emulator/ tests/
```

### Pre-commit Checklist

Before every commit, you MUST:

1. **Run black formatter**: `black .`
2. **Verify formatting passes**: `black --check .`
3. **Run tests**: `pytest`

If `black --check .` reports any formatting issues, run `black .` to fix them before committing.

**DO NOT commit code that fails black formatting checks. This is mandatory.**

## Patterns and Best Practices

### Default Resource Initialization

Some services require default resources to exist on startup. Create an initialization method in `database.py`:

```python
def _init_default_<service>_data(self) -> None:
    """Initialize default <service> resources."""
    # Create default resources like default security groups, networks, etc.
    pass
```

Call this from `Database.__init__()` after initializing storage.

### Resource Relationships

When resources reference other resources, store the ID and provide methods to resolve:

```python
@dataclass
class Port:
    network_id: str  # Reference to Network
    subnet_id: str | None = None  # Optional reference to Subnet

# In database.py, provide lookup methods:
def get_ports_by_network(self, network_id: str) -> list[Port]:
    return [p for p in self._ports.values() if p.network_id == network_id]
```

### MAC Address Generation

OpenStack uses the `fa:16:3e` prefix for MAC addresses:

```python
import random

def _generate_mac_address(self) -> str:
    """Generate a MAC address with OpenStack's fa:16:3e prefix."""
    return "fa:16:3e:{:02x}:{:02x}:{:02x}".format(
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
    )
```

### IP Allocation from Subnets

Track allocated IPs and provide allocation methods:

```python
def _allocate_ip_from_subnet(self, subnet: Subnet) -> str | None:
    """Allocate the next available IP from a subnet's allocation pools."""
    # Parse CIDR, iterate through allocation pools, find unused IP
    # Track used IPs in subnet.used_ips set
    pass
```

### Security Group Default Rules

When creating security groups, add default egress rules to allow all outbound traffic:

```python
# Default egress rules (IPv4 and IPv6)
egress_v4 = SecurityGroupRule(
    security_group_id=sg.id,
    direction="egress",
    ethertype="IPv4",
)
egress_v6 = SecurityGroupRule(
    security_group_id=sg.id,
    direction="egress",
    ethertype="IPv6",
)
```

### Test Database Reset

Reset database state before each test to ensure isolation:

```python
import pytest
from emulator.core.database import db

@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db.reset()
    yield
```

### Cascade Deletes

When deleting parent resources, handle child resources appropriately:

```python
def delete_network(self, network_id: str) -> bool:
    # Check for dependent resources first
    ports = self.get_ports_by_network(network_id)
    if ports:
        raise ConflictError("Network has ports attached")

    subnets = self.get_subnets_by_network(network_id)
    for subnet in subnets:
        self.delete_subnet(subnet.id)

    # Now safe to delete network
    del self._networks[network_id]
    return True
```

### External vs Internal Resources

Some resources have special "external" variants (e.g., external networks for floating IPs):

```python
@dataclass
class Network:
    external: bool = False  # Maps to router:external in API

# In API layer, handle the OpenStack naming convention:
"router:external": network.external
```

## Common OpenStack API Conventions

- Use `X-Auth-Token` header for authentication
- Project ID often appears in URL path: `/v3/{project_id}/resources`
- List responses wrap in plural key: `{"servers": [...]}`
- Single item responses wrap in singular key: `{"server": {...}}`
- Timestamps use ISO 8601 format: `2024-01-15T10:30:00Z`
- UUIDs for all resource IDs
