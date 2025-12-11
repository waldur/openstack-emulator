# OpenStack Emulator

A lightweight OpenStack API emulator for testing purposes. This emulator provides a simplified implementation of OpenStack Nova (Compute), Keystone (Identity), and Cinder (Block Storage) APIs, allowing you to develop and test OpenStack clients without needing a full OpenStack deployment.

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

```bash
# Using the CLI
openstack-emulator

# Or using Python
python -m emulator

# Or using uvicorn directly
uvicorn emulator.api.app:app --host 0.0.0.0 --port 8774
```

The emulator will start on `http://localhost:8774` by default.

### API Documentation

Once running, you can access:
- Swagger UI: http://localhost:8774/docs
- ReDoc: http://localhost:8774/redoc

### Example Usage with OpenStack CLI

```bash
# Set environment variables
export OS_AUTH_URL=http://localhost:8774/v3
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
    auth_url="http://localhost:8774/v3",
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
# Get authentication token
TOKEN=$(curl -s -X POST http://localhost:8774/v3/auth/tokens \
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
# List domains
curl -s http://localhost:8774/v3/domains \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new domain
curl -s -X POST http://localhost:8774/v3/domains \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain": {"name": "my-domain", "description": "My Domain"}}' | jq

# List projects
curl -s http://localhost:8774/v3/projects \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new project
curl -s -X POST http://localhost:8774/v3/projects \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": {"name": "my-project", "description": "My Project"}}' | jq

# List users
curl -s http://localhost:8774/v3/users \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a new user
curl -s -X POST http://localhost:8774/v3/users \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user": {"name": "newuser", "password": "secret123", "email": "user@example.com"}}' | jq

# List roles
curl -s http://localhost:8774/v3/roles \
  -H "X-Auth-Token: $TOKEN" | jq

# Assign role to user on project
curl -s -X PUT "http://localhost:8774/v3/projects/<project-id>/users/<user-id>/roles/<role-id>" \
  -H "X-Auth-Token: $TOKEN"

# List groups
curl -s http://localhost:8774/v3/groups \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a group and add user
curl -s -X POST http://localhost:8774/v3/groups \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"group": {"name": "developers", "description": "Developer group"}}' | jq

# Add user to group
curl -s -X PUT "http://localhost:8774/v3/groups/<group-id>/users/<user-id>" \
  -H "X-Auth-Token: $TOKEN"

# List services
curl -s http://localhost:8774/v3/services \
  -H "X-Auth-Token: $TOKEN" | jq

# List endpoints
curl -s http://localhost:8774/v3/endpoints \
  -H "X-Auth-Token: $TOKEN" | jq

# List regions
curl -s http://localhost:8774/v3/regions \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Cinder API Examples

```bash
# Get project ID from token (needed for Cinder API)
PROJECT_ID=$(curl -s http://localhost:8774/v3/auth/tokens \
  -H "X-Auth-Token: $TOKEN" \
  -H "X-Subject-Token: $TOKEN" | jq -r '.token.project.id')

# List volumes
curl -s "http://localhost:8774/v3/$PROJECT_ID/volumes/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a volume
curl -s -X POST "http://localhost:8774/v3/$PROJECT_ID/volumes" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "my-volume", "size": 10}}' | jq

# Show volume details
curl -s "http://localhost:8774/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN" | jq

# Update a volume
curl -s -X PUT "http://localhost:8774/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "renamed-volume", "description": "Updated description"}}' | jq

# Extend a volume
curl -s -X POST "http://localhost:8774/v3/$PROJECT_ID/volumes/<volume-id>/action" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"os-extend": {"new_size": 20}}'

# Delete a volume
curl -s -X DELETE "http://localhost:8774/v3/$PROJECT_ID/volumes/<volume-id>" \
  -H "X-Auth-Token: $TOKEN"

# List snapshots
curl -s "http://localhost:8774/v3/$PROJECT_ID/snapshots/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a snapshot
curl -s -X POST "http://localhost:8774/v3/$PROJECT_ID/snapshots" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"snapshot": {"name": "my-snapshot", "volume_id": "<volume-id>"}}' | jq

# Delete a snapshot
curl -s -X DELETE "http://localhost:8774/v3/$PROJECT_ID/snapshots/<snapshot-id>" \
  -H "X-Auth-Token: $TOKEN"

# List volume types
curl -s "http://localhost:8774/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a volume type
curl -s -X POST "http://localhost:8774/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume_type": {"name": "ssd", "description": "SSD storage"}}' | jq

# Get volume limits
curl -s "http://localhost:8774/v3/$PROJECT_ID/limits" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Emulator-Specific Endpoints

### Health Check
```
GET /health
```
Returns `{"status": "healthy"}` if the emulator is running.

### Emulator Status
```
GET /emulator/status
```
Returns statistics about the emulator state (number of servers, flavors, images, etc.).

### Reset Emulator
```
POST /emulator/reset
```
Resets the emulator to its initial state, clearing all servers, tokens, and keypairs while preserving default flavors and images.

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
│   │   ├── app.py           # Main FastAPI application
│   │   ├── cinder.py        # Cinder Block Storage API endpoints
│   │   ├── keystone.py      # Keystone Identity API endpoints
│   │   └── nova.py          # Nova Compute API endpoints
│   └── core/
│       ├── __init__.py
│       ├── database.py      # In-memory database
│       └── models.py        # Data models (Server, Flavor, Image, Volume, etc.)
├── tests/
│   ├── __init__.py
│   ├── test_cinder.py       # Cinder API tests
│   ├── test_nova.py         # Nova API tests
│   └── test_keystone.py     # Keystone API tests
├── pyproject.toml           # Project configuration
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
