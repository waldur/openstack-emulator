# Development Guide

This guide covers how to develop and extend the OpenStack Emulator.

## Prerequisites

- Python 3.10+
- pip or uv package manager

## Development Installation

```bash
pip install -e ".[dev]"
```

## Code Style

- Use type hints for all functions
- Use Pydantic `ConfigDict` instead of nested `Config` class
- Use `response_model=None` for routes returning `Response` objects
- Follow OpenStack API patterns for request/response formats

## Pre-commit Requirements

All code must pass these checks before committing:

### 1. Ruff Formatter

The repository is formatted with `ruff format` (not `black`). CI enforces
`ruff format --check .`.

```bash
# Check formatting
uv run ruff format --check .

# Format all files
uv run ruff format .
```

### 2. Ruff Linter

```bash
# Check for errors
uv run ruff check .

# Auto-fix where possible
uv run ruff check --fix .
```

Common issues to avoid:
- **E741**: Ambiguous variable names (use `listener` instead of `l`)
- **F841**: Unused variables

### 3. Mypy Type Checker

```bash
uv run mypy emulator --ignore-missing-imports
```

### 4. Tests

```bash
uv run pytest
uv run pytest --cov=emulator --cov-report=html
```

## Adding a New Service

### 1. Add Models (`emulator/core/models.py`)

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
    project_id: str  # Required for tenant isolation
    status: ResourceStatus = ResourceStatus.ACTIVE
    created_at: str = ""
```

### 2. Add Database Operations (`emulator/core/database.py`)

```python
# In Database.__init__:
self._resources: dict[str, Resource] = {}

# Add CRUD methods with tenant filtering:
def create_resource(self, resource: Resource) -> Resource:
    self._resources[resource.id] = resource
    return resource

def get_resource(self, resource_id: str, project_id: str | None = None) -> Resource | None:
    resource = self._resources.get(resource_id)
    if resource and project_id and resource.project_id != project_id:
        return None
    return resource

def list_resources(self, project_id: str | None = None) -> list[Resource]:
    resources = list(self._resources.values())
    if project_id:
        resources = [r for r in resources if r.project_id == project_id]
    return resources

def delete_resource(self, resource_id: str, project_id: str | None = None) -> bool:
    resource = self._resources.get(resource_id)
    if not resource:
        return False
    if project_id and resource.project_id != project_id:
        return False
    del self._resources[resource_id]
    return True
```

### 3. Create API Routes (`emulator/api/<service>.py`)

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

### 4. Create Standalone App (`emulator/api/app_<service>.py`)

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

### 5. Register Service (`emulator/__init__.py`)

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

### 6. Update Service Catalog (`emulator/core/database.py`)

Add the service to `_generate_service_catalog()`.

### 7. Add Tests (`tests/test_<service>.py`)

```python
import pytest
from fastapi.testclient import TestClient
from emulator.api.app_<service> import app
from emulator.core.database import db

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_database():
    db.reset()
    yield

def test_list_resources():
    response = client.get("/v2/resources")
    assert response.status_code == 200

def test_create_resource():
    response = client.post("/v2/resources", json={"name": "test"})
    assert response.status_code == 201
```

### 8. Update Documentation

- Add API examples to `docs/api-examples.md`
- Update `docs/usage.md` if needed
- Update `README.md` service table

## Standard OpenStack Ports

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

Reference: https://docs.openstack.org/install-guide/firewalls-default-ports.html

## Common Patterns

### MAC Address Generation

```python
def _generate_mac_address(self) -> str:
    """Generate MAC with OpenStack's fa:16:3e prefix."""
    import random
    return "fa:16:3e:{:02x}:{:02x}:{:02x}".format(
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
    )
```

### Default Security Group Rules

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

### Cascade Deletes

```python
def delete_network(self, network_id: str) -> bool:
    # Check for dependent resources first
    ports = self.get_ports_by_network(network_id)
    if ports:
        raise ConflictError("Network has ports attached")

    subnets = self.get_subnets_by_network(network_id)
    for subnet in subnets:
        self.delete_subnet(subnet.id)

    del self._networks[network_id]
    return True
```

## OpenStack API Conventions

- Use `X-Auth-Token` header for authentication
- Project ID in URL path: `/v3/{project_id}/resources`
- List responses: `{"servers": [...]}`
- Single item: `{"server": {...}}`
- Timestamps: ISO 8601 format (`2024-01-15T10:30:00Z`)
- UUIDs for all resource IDs

## Helm chart and release pipeline

The emulator ships a Helm chart at `charts/openstack-emulator/`, published to GitHub Pages at <https://waldur.github.io/openstack-emulator/>. When you change the runtime in a way that affects deployment — adding a port, changing a default flag, introducing a new env var — update the chart in lockstep:

1. **Adding a new service port:** declare it as a named container port in `charts/openstack-emulator/templates/deployment.yaml`, expose it on `service.yaml`, and add a `helm-unittest` assertion in `charts/openstack-emulator/tests/deployment_test.yaml` and `service_test.yaml`.
2. **New CLI flag or config knob:** surface it in `charts/openstack-emulator/values.yaml` with a sane default, wire it into the deployment's `args:`, and add a test case under `charts/openstack-emulator/tests/`.
3. **Run the chart linters locally:**

   ```bash
   helm lint charts/openstack-emulator
   helm unittest charts/openstack-emulator
   helm template ose charts/openstack-emulator/ --debug | less
   ```

4. **Releasing:** push a `X.Y.Z` tag. CI runs the test matrix + chart linters, then publishes a packaged `.tgz` to the `gh-pages` branch on the GitHub mirror. Use the helper:

   ```bash
   uv run scripts/release.py status            # current versions + recent tags
   uv run scripts/release.py check             # local pre-release gates (ruff/mypy/helm)
   uv run scripts/release.py release X.Y.Z     # bump, check, changelog, commit, tag, optionally push
   ```

   The script bumps both `pyproject.toml`'s `[project].version` and `charts/openstack-emulator/Chart.yaml`'s `version:`. `appVersion:` is intentionally left at `"latest"` until the Docker image starts being tag-versioned.

5. **Changelog:** `release` also generates a `CHANGELOG.md` entry via `scripts/changelog.sh`, which categorizes the commits since the previous tag (`scripts/generate_changelog_data.py`), drafts an entry with the `claude` CLI using `scripts/prompts/changelog-prompt.md`, and lets you accept/edit/regenerate it before it's prepended to `CHANGELOG.md` and included in the release commit. This step is **interactive and local-only** (it shells out to `claude`); it is not run in CI. Pass `--skip-changelog` to bypass it, or run `scripts/changelog.sh X.Y.Z` standalone.

## Related Documentation

- [Architecture](./architecture/) - System design
- [Tenant Isolation](./architecture/tenant-isolation.md) - Multi-tenancy patterns
- [Data Models](./architecture/data-models.md) - Model definitions
- [Kubernetes Deployment](./kubernetes.md) - Operator-facing chart install guide
