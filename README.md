# OpenStack Emulator

A lightweight OpenStack API emulator for testing purposes. This emulator provides a simplified implementation of OpenStack Nova (Compute), Keystone (Identity), Cinder (Block Storage), and Glance (Image) APIs, allowing you to develop and test OpenStack clients without needing a full OpenStack deployment.

## Features

- **Nova Compute API (v2.1)**
  - Server lifecycle management (create, list, show, update, delete)
  - Server actions (start, stop, reboot, pause, unpause, suspend, resume, shelve, unshelve)
  - Flavors management
  - Images listing (simplified)
  - Keypairs management
  - Limits and quotas
  - Availability zones
  - Hypervisor statistics

- **Keystone Identity API (v3)**
  - Token authentication (password method)
  - Token validation and revocation
  - Service catalog
  - **Domains**: Full CRUD operations for identity domains
  - **Projects**: Full CRUD operations for projects/tenants
  - **Users**: Full CRUD operations including password management
  - **Roles**: Full CRUD operations and role management
  - **Role Assignments**: Grant/revoke roles to users/groups on projects/domains
  - **Groups**: User group management with membership operations
  - **Services**: Service registry management
  - **Endpoints**: Service endpoint management
  - **Regions**: Region hierarchy management
  - **Credentials**: EC2-style credential management

- **Cinder Block Storage API (v3)**
  - **Volumes**: Full CRUD operations for block storage volumes
  - **Volume Actions**: Extend, attach, detach, set bootable flag
  - **Snapshots**: Create, list, show, update, delete volume snapshots
  - **Volume Types**: Manage volume types with extra specs
  - **Volume Metadata**: Manage volume and snapshot metadata
  - **Limits**: Get volume quotas and usage
  - **Availability Zones**: List storage availability zones

- **Glance Image API (v2)**
  - **Images**: Full CRUD operations for images
  - **Image Data**: Upload and download image files
  - **Image Actions**: Deactivate and reactivate images
  - **Tags**: Add and remove image tags
  - **Image Sharing**: Share images between projects (members)
  - **Visibility**: Public, private, shared, and community images
  - **Schemas**: Image and member schemas

- **Emulator-specific features**
  - In-memory database (no external dependencies)
  - Reset endpoint for testing
  - Status and statistics endpoint
  - Health check endpoint

## Installation

### Using pip

```bash
pip install -e .
```

### Using uv

```bash
uv pip install -e .
```

### Development installation

```bash
pip install -e ".[dev]"
```

## Usage

### Running the emulator

The emulator runs services on their standard OpenStack ports:
- **Keystone (Identity)**: port 5000
- **Nova (Compute)**: port 8774
- **Cinder (Block Storage)**: port 8776
- **Glance (Image)**: port 9292

```bash
# Run all services on standard ports
openstack-emulator

# Run a specific service
openstack-emulator --service=keystone   # Port 5000
openstack-emulator --service=nova       # Port 8774
openstack-emulator --service=cinder     # Port 8776
openstack-emulator --service=glance     # Port 9292

# Or using uvicorn directly for individual services
uvicorn emulator.api.app_keystone:app --host 0.0.0.0 --port 5000
uvicorn emulator.api.app_nova:app --host 0.0.0.0 --port 8774
uvicorn emulator.api.app_cinder:app --host 0.0.0.0 --port 8776
uvicorn emulator.api.app_glance:app --host 0.0.0.0 --port 9292
```

### API Documentation

Once running, you can access Swagger UI for each service:
- Keystone: http://localhost:5000/docs
- Nova: http://localhost:8774/docs
- Cinder: http://localhost:8776/docs
- Glance: http://localhost:9292/docs

### Example Usage with OpenStack CLI

```bash
# Set environment variables (using standard OpenStack ports)
export OS_AUTH_URL=http://localhost:5000/v3
export OS_PROJECT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=secret
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_IDENTITY_API_VERSION=3
export OS_COMPUTE_API_VERSION=2.1
export OS_VOLUME_API_VERSION=3

# List flavors
openstack flavor list

# List images
openstack image list

# Create a server
openstack server create --flavor m1.tiny --image cirros test-server

# List servers
openstack server list

# Show server details
openstack server show test-server

# Stop server
openstack server stop test-server

# Start server
openstack server start test-server

# Delete server
openstack server delete test-server

# List volumes
openstack volume list

# Create a volume
openstack volume create --size 10 my-volume

# Show volume details
openstack volume show my-volume

# Create a snapshot
openstack volume snapshot create --volume my-volume my-snapshot

# List volume types
openstack volume type list

# Delete volume
openstack volume delete my-volume
```

### Example Usage with Python SDK

```python
from openstack import connection

conn = connection.Connection(
    auth_url="http://localhost:5000/v3",
    project_name="admin",
    username="admin",
    password="secret",
    user_domain_name="Default",
    project_domain_name="Default",
)

# List flavors
for flavor in conn.compute.flavors():
    print(flavor.name)

# List images
for image in conn.compute.images():
    print(image.name)

# Create a server
server = conn.compute.create_server(
    name="test-server",
    flavor_id="1",
    image_id=list(conn.compute.images())[0].id,
)

# Wait for server to be active
server = conn.compute.wait_for_server(server)
print(f"Server {server.name} is {server.status}")

# Delete server
conn.compute.delete_server(server)
```

### Example Usage with curl

```bash
# Get authentication token (Keystone on port 5000)
TOKEN=$(curl -s -X POST http://localhost:5000/v3/auth/tokens \
  -H "Content-Type: application/json" \
  -d '{
    "auth": {
      "identity": {
        "methods": ["password"],
        "password": {
          "user": {
            "name": "admin",
            "domain": {"name": "Default"},
            "password": "secret"
          }
        }
      },
      "scope": {
        "project": {
          "name": "admin",
          "domain": {"name": "Default"}
        }
      }
    }
  }' -i | grep X-Subject-Token | cut -d' ' -f2 | tr -d '\r')

# List servers
curl -s http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a server
curl -s -X POST http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server": {
      "name": "test-server",
      "flavorRef": "1",
      "imageRef": "<image-id>"
    }
  }' | jq

# List flavors
curl -s http://localhost:8774/v2.1/flavors/detail \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Keystone API Examples

```bash
# List domains (Keystone on port 5000)
curl -s http://localhost:5000/v3/domains \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new domain
curl -s -X POST http://localhost:5000/v3/domains \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain": {"name": "my-domain", "description": "My Domain"}}' | jq

# List projects
curl -s http://localhost:5000/v3/projects \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new project
curl -s -X POST http://localhost:5000/v3/projects \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": {"name": "my-project", "description": "My Project"}}' | jq

# List users
curl -s http://localhost:5000/v3/users \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new user
curl -s -X POST http://localhost:5000/v3/users \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user": {"name": "newuser", "password": "secret123", "email": "user@example.com"}}' | jq

# List roles
curl -s http://localhost:5000/v3/roles \
  -H "X-Auth-Token: $TOKEN" | jq

# Assign role to user on project
curl -s -X PUT "http://localhost:5000/v3/projects/<project-id>/users/<user-id>/roles/<role-id>" \
  -H "X-Auth-Token: $TOKEN"

# List groups
curl -s http://localhost:5000/v3/groups \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a group and add user
curl -s -X POST http://localhost:5000/v3/groups \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"group": {"name": "developers", "description": "Developer group"}}' | jq

# Add user to group
curl -s -X PUT "http://localhost:5000/v3/groups/<group-id>/users/<user-id>" \
  -H "X-Auth-Token: $TOKEN"

# List services
curl -s http://localhost:5000/v3/services \
  -H "X-Auth-Token: $TOKEN" | jq

# List endpoints
curl -s http://localhost:5000/v3/endpoints \
  -H "X-Auth-Token: $TOKEN" | jq

# List regions
curl -s http://localhost:5000/v3/regions \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Cinder API Examples

```bash
# Get project ID from token (Keystone on port 5000)
PROJECT_ID=$(curl -s http://localhost:5000/v3/auth/tokens \
  -H "X-Auth-Token: $TOKEN" \
  -H "X-Subject-Token: $TOKEN" | jq -r '.token.project.id')

# List volumes (Cinder on port 8776)
curl -s "http://localhost:8776/v3/$PROJECT_ID/volumes/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a volume
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/volumes" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "my-volume", "size": 10}}' | jq

# Show volume details
curl -s "http://localhost:8776/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN" | jq

# Update a volume
curl -s -X PUT "http://localhost:8776/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "renamed-volume", "description": "Updated description"}}' | jq

# Extend a volume
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/volumes/<volume-id>/action" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"os-extend": {"new_size": 20}}'

# Delete a volume
curl -s -X DELETE "http://localhost:8776/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN"

# List snapshots
curl -s "http://localhost:8776/v3/$PROJECT_ID/snapshots/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a snapshot
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/snapshots" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"snapshot": {"name": "my-snapshot", "volume_id": "<volume-id>"}}' | jq

# Delete a snapshot
curl -s -X DELETE "http://localhost:8776/v3/$PROJECT_ID/snapshots/<snapshot-id>" \
  -H "X-Auth-Token: $TOKEN"

# List volume types
curl -s "http://localhost:8776/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a volume type
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume_type": {"name": "ssd", "description": "SSD storage"}}' | jq

# Get volume limits
curl -s "http://localhost:8776/v3/$PROJECT_ID/limits" \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Glance API Examples

```bash
# List images (Glance on port 9292)
curl -s "http://localhost:9292/v2/images" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create an image
curl -s -X POST "http://localhost:9292/v2/images" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-image", "container_format": "bare", "disk_format": "qcow2"}' | jq

# Get image details
curl -s "http://localhost:9292/v2/images/<image-id>" \
  -H "X-Auth-Token: $TOKEN" | jq

# Upload image data
curl -s -X PUT "http://localhost:9292/v2/images/<image-id>/file" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/path/to/image.qcow2

# Update image (using JSON Patch)
curl -s -X PATCH "http://localhost:9292/v2/images/<image-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/openstack-images-v2.1-json-patch" \
  -d '[{"op": "replace", "path": "/name", "value": "new-name"}]' | jq

# Add a tag to an image
curl -s -X PUT "http://localhost:9292/v2/images/<image-id>/tags/my-tag" \
  -H "X-Auth-Token: $TOKEN"

# Delete a tag from an image
curl -s -X DELETE "http://localhost:9292/v2/images/<image-id>/tags/my-tag" \
  -H "X-Auth-Token: $TOKEN"

# Deactivate an image
curl -s -X POST "http://localhost:9292/v2/images/<image-id>/actions/deactivate" \
  -H "X-Auth-Token: $TOKEN"

# Reactivate an image
curl -s -X POST "http://localhost:9292/v2/images/<image-id>/actions/reactivate" \
  -H "X-Auth-Token: $TOKEN"

# Share an image (first set visibility to shared)
curl -s -X PATCH "http://localhost:9292/v2/images/<image-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/openstack-images-v2.1-json-patch" \
  -d '[{"op": "replace", "path": "/visibility", "value": "shared"}]'

# Add a member (share with project)
curl -s -X POST "http://localhost:9292/v2/images/<image-id>/members" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"member": "<project-id>"}' | jq

# List image members
curl -s "http://localhost:9292/v2/images/<image-id>/members" \
  -H "X-Auth-Token: $TOKEN" | jq

# Delete an image
curl -s -X DELETE "http://localhost:9292/v2/images/<image-id>" \
  -H "X-Auth-Token: $TOKEN"
```

## Emulator-Specific Endpoints

### Health Check
Each service provides a health check endpoint:
```
GET http://localhost:5000/health   # Keystone
GET http://localhost:8774/health   # Nova
GET http://localhost:8776/health   # Cinder
GET http://localhost:9292/health   # Glance
```
Returns `{"status": "healthy", "service": "<service-name>"}`.

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=emulator --cov-report=html
```

## Project Structure

```
openstack-emulator/
├── emulator/
│   ├── __init__.py          # Package init and CLI entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py           # Combined FastAPI application (all services)
│   │   ├── app_keystone.py  # Keystone-only app (port 5000)
│   │   ├── app_nova.py      # Nova-only app (port 8774)
│   │   ├── app_cinder.py    # Cinder-only app (port 8776)
│   │   ├── app_glance.py    # Glance-only app (port 9292)
│   │   ├── cinder.py        # Cinder Block Storage API endpoints
│   │   ├── glance.py        # Glance Image API endpoints
│   │   ├── keystone.py      # Keystone Identity API endpoints
│   │   └── nova.py          # Nova Compute API endpoints
│   └── core/
│       ├── __init__.py
│       ├── database.py      # In-memory database
│       └── models.py        # Data models (Server, Flavor, Image, Volume, etc.)
├── tests/
│   ├── __init__.py
│   ├── test_cinder.py       # Cinder API tests
│   ├── test_glance.py       # Glance API tests
│   ├── test_nova.py         # Nova API tests
│   └── test_keystone.py     # Keystone API tests
├── pyproject.toml           # Project configuration
├── CLAUDE.md                # Development guide
└── README.md
```

## Limitations

This is an emulator for testing purposes. It has several limitations compared to a real OpenStack deployment:

- **No real virtualization**: Servers are simulated, not actual VMs
- **Simplified authentication**: Accepts any credentials
- **In-memory storage**: Data is lost when the emulator restarts
- **Limited API coverage**: Only essential endpoints are implemented
- **No networking**: Network operations are simulated
- **Simulated block storage**: Volumes are simulated, not actual block devices
- **Single tenant**: Multi-tenancy is simplified

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

MIT License
