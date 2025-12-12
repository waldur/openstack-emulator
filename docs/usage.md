# Usage Guide

This guide covers how to run and use the OpenStack Emulator.

## Running the Emulator

### Using the CLI

Run all services at once:

```bash
openstack-emulator
```

Run a specific service:

```bash
openstack-emulator --service=keystone   # Port 5000
openstack-emulator --service=nova       # Port 8774
openstack-emulator --service=cinder     # Port 8776
openstack-emulator --service=glance     # Port 9292
openstack-emulator --service=neutron    # Port 9696
openstack-emulator --service=octavia    # Port 9876
openstack-emulator --service=status     # Port 10000 (Web UI)
openstack-emulator --service=scenarios  # Port 8999
```

### Using uvicorn Directly

```bash
uvicorn emulator.api.app_keystone:app --host 0.0.0.0 --port 5000
uvicorn emulator.api.app_nova:app --host 0.0.0.0 --port 8774
uvicorn emulator.api.app_cinder:app --host 0.0.0.0 --port 8776
uvicorn emulator.api.app_glance:app --host 0.0.0.0 --port 9292
uvicorn emulator.api.app_neutron:app --host 0.0.0.0 --port 9696
uvicorn emulator.api.app_octavia:app --host 0.0.0.0 --port 9876
uvicorn emulator.api.app_status:app --host 0.0.0.0 --port 10000
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity service |
| Nova | 8774 | Compute service |
| Cinder | 8776 | Block Storage service |
| Glance | 9292 | Image service |
| Neutron | 9696 | Networking service |
| Octavia | 9876 | Load Balancer service |
| Status UI | 10000 | Web dashboard |
| Scenarios | 8999 | Failure injection API |

## API Documentation (Swagger UI)

Each service provides interactive API documentation:

- Keystone: http://localhost:5000/docs
- Nova: http://localhost:8774/docs
- Cinder: http://localhost:8776/docs
- Glance: http://localhost:9292/docs
- Neutron: http://localhost:9696/docs
- Octavia: http://localhost:9876/docs
- Scenarios: http://localhost:8999/docs

## Status Web UI

The Status Web UI provides a dashboard to monitor and manage the emulator.

**URL**: http://localhost:10000/

### Features

- Service health status
- Resource counts and details by category:
  - **Compute**: Servers, Flavors, Keypairs
  - **Storage**: Images, Volumes, Snapshots
  - **Network**: Networks, Subnets, Ports, Routers, Floating IPs, Security Groups
  - **Identity**: Projects, Users

### Authentication

- Click **Login** to authenticate
- Default credentials: `admin` / `s4l4dus`
- Once authenticated, you can create and delete resources from the UI

### JSON API

```
GET  /api/status        - Get all status information
POST /api/login         - Login with credentials
POST /api/logout        - Logout
GET  /api/session       - Get current session info
```

## Using with OpenStack CLI

### Environment Setup

```bash
export OS_AUTH_URL=http://localhost:5000/v3
export OS_PROJECT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=s4l4dus
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_IDENTITY_API_VERSION=3
export OS_COMPUTE_API_VERSION=2.1
export OS_VOLUME_API_VERSION=3
```

### Common Commands

```bash
# Identity
openstack token issue
openstack project list
openstack user list

# Compute
openstack flavor list
openstack image list
openstack server create --flavor m1.tiny --image cirros test-server
openstack server list
openstack server show test-server
openstack server stop test-server
openstack server start test-server
openstack server delete test-server

# Storage
openstack volume create --size 10 my-volume
openstack volume list
openstack volume show my-volume
openstack volume snapshot create --volume my-volume my-snapshot
openstack volume delete my-volume

# Networking
openstack network list
openstack network create my-network
openstack subnet create --network my-network --subnet-range 10.0.0.0/24 my-subnet
openstack router create my-router
openstack router set --external-gateway external my-router
openstack router add subnet my-router my-subnet
openstack floating ip create external
openstack security group list
openstack security group rule create --protocol tcp --dst-port 22 default
```

## Using with Python SDK

```python
from openstack import connection

conn = connection.Connection(
    auth_url="http://localhost:5000/v3",
    project_name="admin",
    username="admin",
    password="s4l4dus",
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

## Health Checks

Each service provides a health endpoint:

```bash
curl http://localhost:5000/health   # Keystone
curl http://localhost:8774/health   # Nova
curl http://localhost:8776/health   # Cinder
curl http://localhost:9292/health   # Glance
curl http://localhost:9696/health   # Neutron
curl http://localhost:9876/health   # Octavia
curl http://localhost:10000/health  # Status UI
curl http://localhost:8999/health   # Scenarios
```

Returns: `{"status": "healthy", "service": "<service-name>"}`

## Default Resources

The emulator initializes with default resources:

### Flavors
- m1.tiny (1 vCPU, 512MB RAM, 1GB disk)
- m1.small (1 vCPU, 2GB RAM, 20GB disk)
- m1.medium (2 vCPU, 4GB RAM, 40GB disk)
- m1.large (4 vCPU, 8GB RAM, 80GB disk)
- m1.xlarge (8 vCPU, 16GB RAM, 160GB disk)

### Images
- cirros-0.6.2-x86_64
- ubuntu-22.04-server
- debian-12-genericcloud

### Networks
- external (external network for floating IPs)
- private (default private network)
- private-subnet (default subnet: 192.168.1.0/24)

### Identity
- Domain: Default
- Project: admin
- User: admin (password: s4l4dus)
- Roles: admin, member, reader

## Related Documentation

- [API Examples](./api-examples.md) - Detailed curl examples
- [Scenario Injection](./scenarios.md) - Failure testing guide
