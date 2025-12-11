# OpenStack Emulator

A lightweight OpenStack API emulator for testing purposes. This emulator provides a simplified implementation of OpenStack Nova (Compute), Keystone (Identity), Cinder (Block Storage), Glance (Image), and Neutron (Networking) APIs, allowing you to develop and test OpenStack clients without needing a full OpenStack deployment.

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

- **Neutron Networking API (v2.0)**
  - **Networks**: Full CRUD operations for virtual networks
  - **Subnets**: Subnet management with CIDR, DHCP, and allocation pools
  - **Ports**: Port management with fixed IPs and MAC addresses
  - **Routers**: Router management with external gateways
  - **Router Interfaces**: Add/remove router interfaces for subnet connectivity
  - **Floating IPs**: Associate floating IPs with ports for external access
  - **Security Groups**: Full CRUD for security groups
  - **Security Group Rules**: Ingress/egress rules with protocol, port, and CIDR filtering
  - **Extensions**: List supported Neutron API extensions
  - **Default Resources**: Pre-configured external network, private network, and default security group

- **Status Web UI with Authentication**
  - Real-time dashboard showing service status
  - View all resources (servers, volumes, images, networks, etc.)
  - Organized by service (Compute, Storage, Network, Identity)
  - **Authentication**: Login/logout with Keystone credentials
  - **Resource Management**: Create and delete resources from the web UI
    - Servers, Volumes, Images, Snapshots
    - Networks, Subnets, Routers, Floating IPs, Security Groups
    - Projects, Users
  - JSON API endpoint for programmatic access
  - Auto-refresh capability

- **Scenario/Failure Injection System**
  - **Load Simulation**: Inject latency into API responses (0-100% load levels)
  - **Failure Injection**: Simulate service crashes, timeouts, and errors
  - **Built-in Scenarios**: Pre-configured scenarios for common failure modes
    - Service unavailability (Nova OOM, Glance down, etc.)
    - Storage failures (disk full, slow backend)
    - Network issues (partition, latency)
    - Message queue problems (RabbitMQ unstable/down)
    - Database connectivity issues
    - Resource exhaustion (quota exceeded)
  - **Load Presets**: Quick presets (light, moderate, heavy, stressed, chaos)
  - **Gradual Degradation**: Simulate memory leaks with increasing latency
  - **Per-service Targeting**: Apply scenarios to specific services or all
  - **Statistics Tracking**: Monitor injection counts and total delay added
  - **Web UI Integration**: Manage scenarios from the Status UI

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
- **Neutron (Networking)**: port 9696
- **Status (Web UI)**: port 10000
- **Scenarios (Failure Injection)**: port 8999

```bash
# Run all services on standard ports
openstack-emulator

# Run a specific service
openstack-emulator --service=keystone   # Port 5000
openstack-emulator --service=nova       # Port 8774
openstack-emulator --service=cinder     # Port 8776
openstack-emulator --service=glance     # Port 9292
openstack-emulator --service=neutron    # Port 9696
openstack-emulator --service=status     # Port 10000 (Web UI)

# Or using uvicorn directly for individual services
uvicorn emulator.api.app_keystone:app --host 0.0.0.0 --port 5000
uvicorn emulator.api.app_nova:app --host 0.0.0.0 --port 8774
uvicorn emulator.api.app_cinder:app --host 0.0.0.0 --port 8776
uvicorn emulator.api.app_glance:app --host 0.0.0.0 --port 9292
uvicorn emulator.api.app_neutron:app --host 0.0.0.0 --port 9696
uvicorn emulator.api.app_status:app --host 0.0.0.0 --port 10000
```

### API Documentation

Once running, you can access Swagger UI for each service:
- Keystone: http://localhost:5000/docs
- Nova: http://localhost:8774/docs
- Cinder: http://localhost:8776/docs
- Glance: http://localhost:9292/docs
- Neutron: http://localhost:9696/docs
- Status UI: http://localhost:10000/

### Status Web UI

The Status Web UI provides a real-time dashboard to view and manage the state of the emulator:

- **Dashboard URL**: http://localhost:10000/
- **JSON API**: http://localhost:10000/api/status

**Features:**
- Service health status (running/offline)
- Resource counts and details organized by tabs:
  - **Compute**: Servers, Flavors, Keypairs
  - **Storage**: Images, Volumes, Snapshots
  - **Network**: Networks, Subnets, Ports, Routers, Floating IPs, Security Groups
  - **Identity**: Projects, Users

**Authentication:**
- Click **Login** to authenticate with Keystone credentials
- Default credentials: `admin` / any password (emulator accepts any password)
- Once logged in, you can create and delete resources directly from the web interface

**Management API Endpoints:**
When authenticated, the following REST APIs are available:
```
POST   /api/login          - Login with username/password
POST   /api/logout         - Logout and revoke session
GET    /api/session        - Get current session info

POST   /api/servers        - Create a server
DELETE /api/servers/{id}   - Delete a server
POST   /api/servers/{id}/action - Server actions (start/stop)

POST   /api/volumes        - Create a volume
DELETE /api/volumes/{id}   - Delete a volume

POST   /api/networks       - Create a network
DELETE /api/networks/{id}  - Delete a network

POST   /api/subnets        - Create a subnet
DELETE /api/subnets/{id}   - Delete a subnet

POST   /api/routers        - Create a router
DELETE /api/routers/{id}   - Delete a router

POST   /api/floating_ips   - Allocate a floating IP
DELETE /api/floating_ips/{id} - Release a floating IP

POST   /api/security_groups - Create a security group
DELETE /api/security_groups/{id} - Delete a security group

POST   /api/projects       - Create a project
DELETE /api/projects/{id}  - Delete a project

POST   /api/users          - Create a user
DELETE /api/users/{id}     - Delete a user

POST   /api/images         - Create an image
DELETE /api/images/{id}    - Delete an image

POST   /api/snapshots      - Create a snapshot
DELETE /api/snapshots/{id} - Delete a snapshot
```

The page auto-refreshes every 30 seconds. Use the JSON API endpoint for programmatic access to status information.

### Scenario/Failure Injection

The Scenario service allows you to simulate various failure conditions to test your OpenStack client's resilience.

- **Scenarios API**: http://localhost:8999/
- **Swagger UI**: http://localhost:8999/docs
- **Web UI**: Available in the Status UI "Scenarios" tab (http://localhost:8000/)

**Built-in Scenarios:**

| Category | Scenario | Description |
|----------|----------|-------------|
| Performance | `light_load` | Light system load (100-500ms delays) |
| Performance | `system_under_load` | Moderate load (500-3000ms delays) |
| Performance | `heavy_load` | Heavy load with spikes |
| Performance | `system_stressed` | Severe load with timeouts |
| Performance | `gradual_degradation` | Increasing latency over time |
| Service Crash | `nova_oom_crash` | Nova returns 503 errors |
| Service Crash | `glance_unavailable` | Glance returns 503 errors |
| Storage | `cinder_disk_full` | Volume creation fails |
| Storage | `slow_storage_backend` | High latency storage ops |
| Network | `neutron_network_partition` | Random network failures |
| Message Queue | `rabbitmq_unstable` | Intermittent failures |
| Message Queue | `rabbitmq_down` | Complete MQ failure |
| Database | `database_connection_lost` | DB connectivity failure |
| Resource | `quota_exceeded` | Create operations fail |
| Auth | `keystone_overloaded` | Auth rate limiting |

**API Endpoints:**

```bash
# List all available scenarios
curl http://localhost:8999/scenarios | jq

# Get active scenarios
curl http://localhost:8999/scenarios/active | jq

# Enable a scenario
curl -X POST http://localhost:8999/scenarios/heavy_load/enable | jq

# Disable a scenario
curl -X POST http://localhost:8999/scenarios/heavy_load/disable | jq

# Reset all scenarios
curl -X POST http://localhost:8999/scenarios/reset | jq

# Apply a preset (light, moderate, heavy, stressed, chaos)
curl -X POST http://localhost:8999/scenarios/preset/heavy | jq

# Set load level (0-100%)
curl -X POST http://localhost:8999/scenarios/load \
  -H "Content-Type: application/json" \
  -d '{"level": 50}' | jq

# Get injection statistics
curl http://localhost:8999/scenarios/stats | jq

# Create a custom scenario
curl -X POST http://localhost:8999/scenarios/custom \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_scenario",
    "name": "My Custom Scenario",
    "description": "Custom test scenario",
    "category": "performance",
    "failureType": "slow_response",
    "loadProfile": {
      "minDelayMs": 500,
      "maxDelayMs": 2000
    }
  }' | jq
```

**Example: Testing with Failure Injection**

```bash
# Enable Nova crash scenario
curl -X POST http://localhost:8999/scenarios/nova_oom_crash/enable

# Now Nova API calls will fail with 503
curl -s http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN"
# Returns: {"error": {"message": "Service Unavailable...", "code": 503}}

# Disable the scenario
curl -X POST http://localhost:8999/scenarios/nova_oom_crash/disable
```

**Example: Load Testing**

```bash
# Set 50% load level (adds latency to all requests)
curl -X POST http://localhost:8999/scenarios/load \
  -H "Content-Type: application/json" \
  -d '{"level": 50}'

# API calls now have artificial delays
time curl -s http://localhost:8774/v2.1/flavors \
  -H "X-Auth-Token: $TOKEN"
# real    0m1.234s  (includes injected delay)

# Reset to normal
curl -X POST http://localhost:8999/scenarios/reset
```

**Cross-Process State Sharing:**

When running multiple services as separate processes (the default mode), the Scenario service shares state with other services via a file-based mechanism:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Process Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Scenarios Service (8999)         Nova Service (8774)           │
│  ┌─────────────────────┐         ┌─────────────────────┐        │
│  │ POST /enable        │         │ ScenarioMiddleware  │        │
│  │       │             │         │       │             │        │
│  │       ▼             │         │       ▼             │        │
│  │  Write to file ─────┼─────────┼──► Read from file   │        │
│  └─────────────────────┘         └─────────────────────┘        │
│                                                                  │
│  State File: /tmp/openstack-emulator-scenarios.json             │
└─────────────────────────────────────────────────────────────────┘
```

- **State File**: Enabled scenarios are persisted to `/tmp/openstack-emulator-scenarios.json`
- **File Locking**: Uses `fcntl` for safe concurrent access across processes
- **Caching**: State is cached with a 0.5-second TTL to minimize file reads
- **Automatic Sync**: Middleware reads shared state before processing each request

This architecture ensures that when you enable a scenario via the Scenarios API, all service processes (Nova, Keystone, Cinder, etc.) immediately start applying the configured failures and delays.

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

# List networks
openstack network list

# Create a network
openstack network create my-network

# Create a subnet
openstack subnet create --network my-network --subnet-range 10.0.0.0/24 my-subnet

# List routers
openstack router list

# Create a router with external gateway
openstack router create --external-gateway external my-router

# Add subnet to router
openstack router add subnet my-router my-subnet

# Create a floating IP
openstack floating ip create external

# List security groups
openstack security group list

# Create a security group rule
openstack security group rule create --protocol tcp --dst-port 22 default
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

### Neutron API Examples

```bash
# List networks (Neutron on port 9696)
curl -s "http://localhost:9696/v2.0/networks" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a network
curl -s -X POST "http://localhost:9696/v2.0/networks" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"network": {"name": "my-network", "admin_state_up": true}}' | jq

# Get network details
curl -s "http://localhost:9696/v2.0/networks/<network-id>" \
  -H "X-Auth-Token: $TOKEN" | jq

# List subnets
curl -s "http://localhost:9696/v2.0/subnets" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a subnet
curl -s -X POST "http://localhost:9696/v2.0/subnets" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subnet": {"name": "my-subnet", "network_id": "<network-id>", "ip_version": 4, "cidr": "10.0.0.0/24"}}' | jq

# List ports
curl -s "http://localhost:9696/v2.0/ports" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a port
curl -s -X POST "http://localhost:9696/v2.0/ports" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"port": {"name": "my-port", "network_id": "<network-id>"}}' | jq

# List routers
curl -s "http://localhost:9696/v2.0/routers" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a router
curl -s -X POST "http://localhost:9696/v2.0/routers" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"router": {"name": "my-router", "admin_state_up": true}}' | jq

# Set external gateway on router
curl -s -X PUT "http://localhost:9696/v2.0/routers/<router-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"router": {"external_gateway_info": {"network_id": "<external-network-id>"}}}' | jq

# Add router interface (connect subnet to router)
curl -s -X PUT "http://localhost:9696/v2.0/routers/<router-id>/add_router_interface" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subnet_id": "<subnet-id>"}' | jq

# Remove router interface
curl -s -X PUT "http://localhost:9696/v2.0/routers/<router-id>/remove_router_interface" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subnet_id": "<subnet-id>"}' | jq

# List floating IPs
curl -s "http://localhost:9696/v2.0/floatingips" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a floating IP
curl -s -X POST "http://localhost:9696/v2.0/floatingips" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"floatingip": {"floating_network_id": "<external-network-id>"}}' | jq

# Associate floating IP with a port
curl -s -X PUT "http://localhost:9696/v2.0/floatingips/<floatingip-id>" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"floatingip": {"port_id": "<port-id>"}}' | jq

# List security groups
curl -s "http://localhost:9696/v2.0/security-groups" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a security group
curl -s -X POST "http://localhost:9696/v2.0/security-groups" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"security_group": {"name": "web-servers", "description": "Security group for web servers"}}' | jq

# List security group rules
curl -s "http://localhost:9696/v2.0/security-group-rules" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create a security group rule (allow SSH)
curl -s -X POST "http://localhost:9696/v2.0/security-group-rules" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"security_group_rule": {"security_group_id": "<security-group-id>", "direction": "ingress", "protocol": "tcp", "port_range_min": 22, "port_range_max": 22, "remote_ip_prefix": "0.0.0.0/0"}}' | jq

# Create a security group rule (allow HTTP)
curl -s -X POST "http://localhost:9696/v2.0/security-group-rules" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"security_group_rule": {"security_group_id": "<security-group-id>", "direction": "ingress", "protocol": "tcp", "port_range_min": 80, "port_range_max": 80, "remote_ip_prefix": "0.0.0.0/0"}}' | jq

# Delete a security group rule
curl -s -X DELETE "http://localhost:9696/v2.0/security-group-rules/<rule-id>" \
  -H "X-Auth-Token: $TOKEN"

# Delete a security group
curl -s -X DELETE "http://localhost:9696/v2.0/security-groups/<security-group-id>" \
  -H "X-Auth-Token: $TOKEN"

# List Neutron extensions
curl -s "http://localhost:9696/v2.0/extensions" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Emulator-Specific Endpoints

### Health Check
Each service provides a health check endpoint:
```
GET http://localhost:5000/health   # Keystone
GET http://localhost:8774/health   # Nova
GET http://localhost:8776/health   # Cinder
GET http://localhost:9292/health   # Glance
GET http://localhost:9696/health   # Neutron
GET http://localhost:10000/health  # Status UI
GET http://localhost:8999/health   # Scenarios
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
│   │   ├── app_neutron.py   # Neutron-only app (port 9696)
│   │   ├── app_status.py    # Status Web UI app (port 10000)
│   │   ├── app_scenarios.py # Scenarios API app (port 8999)
│   │   ├── cinder.py        # Cinder Block Storage API endpoints
│   │   ├── glance.py        # Glance Image API endpoints
│   │   ├── keystone.py      # Keystone Identity API endpoints
│   │   ├── neutron.py       # Neutron Networking API endpoints
│   │   ├── nova.py          # Nova Compute API endpoints
│   │   ├── scenarios.py     # Scenario management API endpoints
│   │   └── status_ui.py     # Status Web UI routes
│   └── core/
│       ├── __init__.py
│       ├── database.py      # In-memory database
│       ├── middleware.py    # Scenario injection middleware
│       ├── models.py        # Data models (Server, Flavor, Image, Volume, Network, etc.)
│       ├── scenarios.py     # Scenario models and definitions
│       ├── scenario_manager.py  # Scenario state and injection logic
│       └── shared_state.py  # Cross-process state sharing for scenarios
├── tests/
│   ├── __init__.py
│   ├── test_cinder.py       # Cinder API tests
│   ├── test_glance.py       # Glance API tests
│   ├── test_keystone.py     # Keystone API tests
│   ├── test_neutron.py      # Neutron API tests
│   ├── test_nova.py         # Nova API tests
│   ├── test_scenarios.py    # Scenario injection tests
│   └── test_status.py       # Status UI tests
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
- **Simulated networking**: Networks, ports, and routers are emulated but don't route traffic
- **Simulated block storage**: Volumes are simulated, not actual block devices
- **Single tenant**: Multi-tenancy is simplified

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

MIT License
