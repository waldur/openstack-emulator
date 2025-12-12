# Tenant Isolation

This document describes how the OpenStack Emulator implements multi-tenancy and resource isolation between projects (tenants).

## Overview

OpenStack uses an identity model where domains contain users, groups, and projects as peers. Users gain access to project resources through role assignments:

```
Domain
  ├── Users
  ├── Groups
  └── Projects (Tenants)
        └── Resources (Servers, Volumes, Networks, etc.)

Role Assignments link Users/Groups to Projects/Domains:

  User ──┬── Role ──► Project (scoped access)
         └── Role ──► Domain  (domain-wide access)

  Group ─┬── Role ──► Project
         └── Role ──► Domain
```

**Key concepts:**
- **Users belong to Domains**, not Projects
- **Projects belong to Domains** and contain resources
- **Role Assignments** grant users/groups specific roles on projects or domains
- A user can have different roles on different projects

The emulator implements tenant isolation to ensure resources belonging to one project are not accessible to other projects, mimicking real OpenStack behavior.

For more details on OpenStack identity concepts, see [Keystone Identity Concepts](https://docs.openstack.org/keystone/latest/admin/identity-concepts.html).

## Resource Isolation Categories

### 1. Project-Scoped Resources (Full Isolation)

These resources belong to a specific project and are isolated by default:

| Service | Resource | Isolation Field | Notes |
|---------|----------|-----------------|-------|
| Nova | Server | `tenant_id` | Also tracks `user_id` |
| Nova | ServerGroup | `project_id` | Also tracks `user_id` |
| Nova | Keypair | `user_id` | User-scoped, not project-scoped |
| Cinder | Volume | `project_id` | Also tracks `user_id` |
| Cinder | Snapshot | `project_id` | Also tracks `user_id` |
| Neutron | Network | `project_id` | Can be shared via `shared` flag |
| Neutron | Subnet | `project_id` | |
| Neutron | Port | `project_id` | |
| Neutron | Router | `project_id` | |
| Neutron | FloatingIP | `project_id` | |
| Neutron | SecurityGroup | `project_id` | Default created per project |
| Neutron | SecurityGroupRule | `project_id` | |
| Glance | Image | `owner` | Visibility controls access |
| Octavia | LoadBalancer | `project_id` | |
| Octavia | Listener | `project_id` | |
| Octavia | Pool | `project_id` | |
| Octavia | Member | `project_id` | |
| Octavia | HealthMonitor | `project_id` | |
| Octavia | L7Policy | `project_id` | |
| Octavia | L7Rule | `project_id` | |

### 2. Global Resources (No Isolation)

These resources are shared across all projects:

| Service | Resource | Access Control |
|---------|----------|----------------|
| Nova | Flavor | `is_public` flag controls visibility |
| Keystone | Domain | Admin-only management |
| Keystone | Region | Admin-only management |
| Keystone | Service | Admin-only management |
| Keystone | Endpoint | Admin-only management |
| Keystone | Role | Admin-only management |
| Cinder | VolumeType | `is_public` flag controls visibility |
| Cinder | QosSpec | Admin-only management |

### 3. Domain-Scoped Resources

These resources are scoped to identity domains:

| Service | Resource | Scope Field |
|---------|----------|-------------|
| Keystone | Project | `domain_id` |
| Keystone | User | `domain_id` |
| Keystone | Group | `domain_id` |
| Keystone | Role (optional) | `domain_id` |

### 4. User-Scoped Resources

These resources belong to specific users:

| Service | Resource | Scope Field | Notes |
|---------|----------|-------------|-------|
| Nova | Keypair | `user_id` | Keyed as `user_id:name` |
| Keystone | Credential | `user_id` | Optional `project_id` |
| Keystone | Token | `user_id` | Session-based |

## Isolation Implementation

### List Operations

Most list operations support tenant filtering:

```python
# List volumes for a specific project
def list_volumes(
    self,
    project_id: str | None = None,
    all_tenants: bool = False,
) -> list[Volume]:
    volumes = list(self._volumes.values())
    if project_id and not all_tenants:
        volumes = [v for v in volumes if v.project_id == project_id]
    return volumes
```

### Get Operations

Get operations optionally verify ownership:

```python
# Get volume with ownership check
def get_volume(
    self,
    volume_id: str,
    project_id: str | None = None
) -> Volume | None:
    volume = self._volumes.get(volume_id)
    if volume is None:
        return None
    if project_id is not None and volume.project_id != project_id:
        return None  # Not owned by this project
    return volume
```

### Modification Operations

Update and delete operations verify ownership:

```python
# Delete only if owned
def delete_volume(
    self,
    volume_id: str,
    project_id: str | None = None
) -> bool:
    volume = self._volumes.get(volume_id)
    if not volume:
        return False
    if project_id is not None and volume.project_id != project_id:
        return False  # Cannot delete other project's resources
    del self._volumes[volume_id]
    return True
```

## Special Cases

### Security Groups

Each project gets a `default` security group created automatically:

```python
def _ensure_default_security_group(self, project_id: str) -> SecurityGroup:
    """Ensure default security group exists for project."""
    existing = self.get_security_group_by_name("default", project_id)
    if existing:
        return existing

    # Create with default egress rules
    sg = SecurityGroup(
        name="default",
        project_id=project_id,
        description="Default security group",
    )
    # Add default egress rules...
    return sg
```

### Network Sharing

Networks can be shared between projects via:

1. **`shared` flag**: Makes network visible to all projects
2. **`external` flag**: Makes network available as external gateway
3. **RBAC Policies**: Fine-grained sharing control

```python
@dataclass
class Network:
    project_id: str = ""
    shared: bool = False      # Visible to all projects
    external: bool = False    # router:external in API

@dataclass
class RbacPolicy:
    object_type: str = "network"
    object_id: str = ""
    target_project: str = ""  # '*' for all, or specific project_id
    action: str = "access_as_shared"
```

### Image Visibility

Glance images have a visibility model:

| Visibility | Description |
|------------|-------------|
| `public` | Visible to all projects |
| `private` | Only visible to owner |
| `shared` | Visible to specific projects via members |
| `community` | Visible to all, managed by community |

```python
@dataclass
class GlanceImage:
    owner: str = ""  # project_id
    visibility: ImageVisibility = ImageVisibility.PRIVATE
```

Image members allow sharing with specific projects:

```python
@dataclass
class ImageMember:
    image_id: str = ""
    member_id: str = ""  # project_id to share with
    status: str = "pending"  # pending, accepted, rejected
```

### Admin Access

The `all_tenants` parameter allows admin users to bypass tenant filtering:

```python
# Admin listing all volumes across tenants
volumes = db.list_volumes(all_tenants=True)

# Regular user listing only their volumes
volumes = db.list_volumes(project_id="user-project-id")
```

## Quotas

Each project has independent quotas:

| Service | Quota Model | Resources Tracked |
|---------|-------------|-------------------|
| Nova | `NovaQuota` | instances, cores, ram, keypairs, server_groups |
| Neutron | `NeutronQuota` | networks, subnets, ports, routers, floatingips, security_groups |
| Cinder | `CinderQuota` | volumes, snapshots, gigabytes, backups |

```python
@dataclass
class NovaQuota:
    project_id: str = ""
    instances: int = 10
    cores: int = 20
    ram: int = 51200  # MB
    # ...
```

## Testing Isolation

When writing tests, ensure proper isolation by resetting the database:

```python
import pytest
from emulator.core.database import db

@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db.reset()
    yield
```

For multi-tenant tests, create separate projects and verify isolation:

```python
def test_volume_isolation():
    # Create volumes in different projects
    vol1 = db.create_volume("vol1", 10, project_id="project-a", user_id="user-a")
    vol2 = db.create_volume("vol2", 10, project_id="project-b", user_id="user-b")

    # Verify isolation
    assert db.get_volume(vol1.id, project_id="project-a") is not None
    assert db.get_volume(vol1.id, project_id="project-b") is None  # Can't see other project's volume

    # Verify list isolation
    project_a_volumes = db.list_volumes(project_id="project-a")
    assert len(project_a_volumes) == 1
    assert project_a_volumes[0].id == vol1.id
```

## Current Limitations

1. **No Policy Enforcement**: The emulator does not implement OpenStack's policy.json rules
2. **Simplified Admin Check**: Admin access is not fully implemented; `all_tenants` is trust-based
3. **No Ownership Transfer**: Resources cannot be transferred between projects
4. **No Hierarchical Projects**: Project hierarchy (parent_id) is stored but not enforced

## Related Documentation

- [Data Models](./data-models.md) - Detailed model definitions
- [Architecture Overview](./README.md) - System architecture
