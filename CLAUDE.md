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
