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
openstack-emulator --service=placement  # Port 8778
openstack-emulator --service=swift      # Port 8080
openstack-emulator --service=status     # Port 10000 (Web UI)
openstack-emulator --service=scenarios  # Port 8999
```

### Using uvicorn Directly

There are no per-service app modules to point uvicorn at; the apps are built by
`create_all_service_apps()` and keyed by service name. Use a factory:

```bash
uvicorn --factory --host 0.0.0.0 --port 5000 \
  'emulator.api.unified_app:create_all_service_apps()["keystone"]'
```

In practice `openstack-emulator --service=<name>` is the supported way to run a
single service, since it also applies `--port-offset`, presets and persistence.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity service |
| Nova | 8774 | Compute service |
| Cinder | 8776 | Block Storage service |
| Glance | 9292 | Image service |
| Neutron | 9696 | Networking service |
| Octavia | 9876 | Load Balancer service |
| Placement | 8778 | Resource Provider service |
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
- Placement: http://localhost:8778/docs
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
curl http://localhost:8778/health   # Placement
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

## Seeding sample resources with presets

The emulator ships seven built-in presets that add projects, networks, servers, volumes, and so on at startup. Bundled with the installed package at `emulator/presets/*.yaml`:

| Preset | Use case |
|---|---|
| `empty` | Only the default domain/project/user/flavors — no extra resources |
| `development` | Small dev env with a project, network, sample servers, a keypair |
| `production` | Multiple projects, networks, servers, a load balancer |
| `enterprise` | Multi-department layout with a DMZ and shared services |
| `microservices` | Service-mesh + API gateway + observability stack |
| `multi-tier` | Strict network segmentation across availability zones |
| `stress-test` | 100+ servers / 50+ volumes for scale tests |

Load one on startup:

```bash
openstack-emulator --preset development
openstack-emulator --list-presets        # list the built-ins
```

Load a custom preset from disk (mirror the schema of any built-in file):

```bash
openstack-emulator --preset-file ./my-preset.yaml
```

In Kubernetes the same flags are surfaced as the `preset.name` and `customPreset.{enabled,yaml}` chart values — see [Kubernetes Deployment](./kubernetes.md).

## Related Documentation

- [API Examples](./api-examples.md) - Detailed curl examples
- [Scenario Injection](./scenarios.md) - Failure testing guide
- [Kubernetes Deployment](./kubernetes.md) - Helm chart install and operator guide
