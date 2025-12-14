# OpenStack Emulator - AI Assistant Guide

This file contains instructions for AI assistants developing and extending the OpenStack emulator.

## Project Overview

This is a lightweight OpenStack API emulator for testing purposes. It provides simplified implementations of OpenStack services that can be used to develop and test OpenStack clients without a full OpenStack deployment.

## Documentation Structure

The project documentation is organized as follows:

```
docs/
├── architecture/
│   ├── README.md           # Architecture overview
│   ├── data-models.md      # Data model definitions
│   └── tenant-isolation.md # Multi-tenancy documentation
├── development.md          # Development guide (code style, adding services)
├── usage.md                # Usage guide
├── api-examples.md         # API examples (curl, SDK)
└── scenarios.md            # Failure injection guide
```

When making changes, update the appropriate documentation:
- **Architecture changes**: Update `docs/architecture/`
- **New API endpoints**: Add examples to `docs/api-examples.md`
- **Usage changes**: Update `docs/usage.md`
- **Development patterns**: Update `docs/development.md`
- **New features**: Update `README.md` if significant

Keep `README.md` minimal with links to detailed docs.

## Architecture

- **FastAPI**: REST API framework
- **Pydantic**: Request/response validation
- **In-memory database**: No external dependencies
- **Multiprocessing**: Each service runs on its own port

For detailed documentation:
- [Architecture Overview](docs/architecture/README.md)
- [Development Guide](docs/development.md)

## Pre-commit Requirements

**IMPORTANT: You MUST run all linters and ensure they pass before committing any code.**

Before every commit, run these commands in order:

1. **Run black formatter**: `black emulator tests`
2. **Run ruff linter**: `ruff check emulator tests`
3. **Run mypy type checker**: `mypy emulator --ignore-missing-imports`
4. **Run tests**: `pytest`

All four checks must pass before committing. Fix any errors before proceeding.

**DO NOT commit code that fails any of these checks. This is mandatory.**

## Tenant Isolation Requirements

When implementing new resources, follow these tenant isolation patterns:

### Project-Scoped Resources

Most resources should be scoped to a project (tenant). Include these fields:

```python
@dataclass
class Resource:
    id: str
    name: str
    project_id: str  # Required for tenant isolation
    user_id: str     # Optional: track creating user
```

### Database Operations with Tenant Filtering

Implement filtering in list operations:

```python
def list_resources(
    self,
    project_id: str | None = None,
    all_tenants: bool = False,
) -> list[Resource]:
    resources = list(self._resources.values())
    if project_id and not all_tenants:
        resources = [r for r in resources if r.project_id == project_id]
    return resources
```

Implement ownership verification in get/update/delete:

```python
def get_resource(
    self,
    resource_id: str,
    project_id: str | None = None
) -> Resource | None:
    resource = self._resources.get(resource_id)
    if resource is None:
        return None
    if project_id is not None and resource.project_id != project_id:
        return None  # Deny access to other project's resource
    return resource
```

### Resource Categories

| Category | Isolation | Examples |
|----------|-----------|----------|
| Project-scoped | Full isolation by `project_id` | Servers, Volumes, Networks, Routers |
| User-scoped | Isolated by `user_id` | Keypairs, Credentials |
| Domain-scoped | Isolated by `domain_id` | Projects, Users, Groups |
| Global | No isolation (admin-managed) | Flavors, VolumeTypes, Regions |
| Shared | Visibility controls | Images (public/private/shared), Networks (shared flag) |

For detailed tenant isolation documentation, see [docs/architecture/tenant-isolation.md](docs/architecture/tenant-isolation.md).

## Common OpenStack API Conventions

- Use `X-Auth-Token` header for authentication
- Project ID often appears in URL path: `/v3/{project_id}/resources`
- List responses wrap in plural key: `{"servers": [...]}`
- Single item responses wrap in singular key: `{"server": {...}}`
- Timestamps use ISO 8601 format: `2024-01-15T10:30:00Z`
- UUIDs for all resource IDs

## Standard OpenStack Service Ports

| Service | Port |
|---------|------|
| Keystone | 5000 |
| Nova | 8774 |
| Cinder | 8776 |
| Glance | 9292 |
| Neutron | 9696 |
| Octavia | 9876 |

For full port list and development instructions, see [docs/development.md](docs/development.md).

## API Compliance Testing

**IMPORTANT: When adding or modifying API endpoints, ensure compliance with OpenStack specifications.**

The emulator includes automated tools to compare our API implementation with official OpenStack OpenAPI specifications:

### Quick Compliance Check

```bash
# Start the emulator
openstack-emulator

# Run API compliance analysis  
scripts/check-api-compliance.sh

# Generate summary report
python3 scripts/generate_compliance_report.py reports/
```

### Key Files

- **Documentation**: [docs/api-compliance.md](docs/api-compliance.md) - Complete testing process
- **Main script**: `scripts/check-api-compliance.sh` - Export specs and run comparisons  
- **Analysis tool**: `scripts/compare_apis.py` - Detailed endpoint/schema comparison
- **Report generator**: `scripts/generate_compliance_report.py` - Summary dashboard

### Workflow Integration

1. **Before implementing new endpoints**: Check official OpenStack specs (auto-downloaded from https://github.com/gtema/openstack)
2. **After API changes**: Run compliance check to verify alignment
3. **Before releases**: Generate full compliance report for documentation

The tools automatically:
- Export OpenAPI specs from running emulator services
- Compare with official OpenStack specifications  
- Generate detailed gap analysis and coverage reports
- Provide actionable recommendations for missing endpoints

See [docs/api-compliance.md](docs/api-compliance.md) for complete documentation and setup instructions.
