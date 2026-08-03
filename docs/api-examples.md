# API Examples

This document provides curl examples for interacting with the OpenStack Emulator APIs.

## Authentication

### Get a Token

```bash
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
            "password": "s4l4dus"
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

echo $TOKEN
```

### Get Project ID

```bash
PROJECT_ID=$(curl -s http://localhost:5000/v3/auth/tokens \
  -H "X-Auth-Token: $TOKEN" \
  -H "X-Subject-Token: $TOKEN" | jq -r '.token.project.id')

echo $PROJECT_ID
```

## Keystone (Identity)

### Domains

```bash
# List domains
curl -s http://localhost:5000/v3/domains \
  -H "X-Auth-Token: $TOKEN" | jq

# Create domain
curl -s -X POST http://localhost:5000/v3/domains \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain": {"name": "my-domain", "description": "My Domain"}}' | jq

# Get domain
curl -s http://localhost:5000/v3/domains/{domain_id} \
  -H "X-Auth-Token: $TOKEN" | jq

# Delete domain
curl -s -X DELETE http://localhost:5000/v3/domains/{domain_id} \
  -H "X-Auth-Token: $TOKEN"
```

### Projects

```bash
# List projects
curl -s http://localhost:5000/v3/projects \
  -H "X-Auth-Token: $TOKEN" | jq

# Create project
curl -s -X POST http://localhost:5000/v3/projects \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": {"name": "my-project", "description": "My Project"}}' | jq

# Update project
curl -s -X PATCH http://localhost:5000/v3/projects/{project_id} \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": {"description": "Updated description"}}' | jq

# Delete project
curl -s -X DELETE http://localhost:5000/v3/projects/{project_id} \
  -H "X-Auth-Token: $TOKEN"
```

### Users

```bash
# List users
curl -s http://localhost:5000/v3/users \
  -H "X-Auth-Token: $TOKEN" | jq

# Create user
curl -s -X POST http://localhost:5000/v3/users \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user": {"name": "newuser", "password": "secret123", "email": "user@example.com"}}' | jq

# Update user password
curl -s -X POST http://localhost:5000/v3/users/{user_id}/password \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user": {"password": "newpassword", "original_password": "oldpassword"}}'

# Delete user
curl -s -X DELETE http://localhost:5000/v3/users/{user_id} \
  -H "X-Auth-Token: $TOKEN"
```

### Roles

```bash
# List roles
curl -s http://localhost:5000/v3/roles \
  -H "X-Auth-Token: $TOKEN" | jq

# Assign role to user on project
curl -s -X PUT "http://localhost:5000/v3/projects/{project_id}/users/{user_id}/roles/{role_id}" \
  -H "X-Auth-Token: $TOKEN"

# Check role assignment
curl -s -X HEAD "http://localhost:5000/v3/projects/{project_id}/users/{user_id}/roles/{role_id}" \
  -H "X-Auth-Token: $TOKEN"

# Revoke role
curl -s -X DELETE "http://localhost:5000/v3/projects/{project_id}/users/{user_id}/roles/{role_id}" \
  -H "X-Auth-Token: $TOKEN"

# List role assignments
curl -s "http://localhost:5000/v3/role_assignments" \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Groups

```bash
# Create group
curl -s -X POST http://localhost:5000/v3/groups \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"group": {"name": "developers", "description": "Developer group"}}' | jq

# Add user to group
curl -s -X PUT "http://localhost:5000/v3/groups/{group_id}/users/{user_id}" \
  -H "X-Auth-Token: $TOKEN"

# List group users
curl -s "http://localhost:5000/v3/groups/{group_id}/users" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Nova (Compute)

### Servers

```bash
# List servers
curl -s http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN" | jq

# List servers (detailed)
curl -s http://localhost:8774/v2.1/servers/detail \
  -H "X-Auth-Token: $TOKEN" | jq

# Create server
curl -s -X POST http://localhost:8774/v2.1/servers \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server": {
      "name": "test-server",
      "flavorRef": "1",
      "imageRef": "{image_id}"
    }
  }' | jq

# Get server
curl -s http://localhost:8774/v2.1/servers/{server_id} \
  -H "X-Auth-Token: $TOKEN" | jq

# Server actions
curl -s -X POST http://localhost:8774/v2.1/servers/{server_id}/action \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"os-stop": null}'

curl -s -X POST http://localhost:8774/v2.1/servers/{server_id}/action \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"os-start": null}'

curl -s -X POST http://localhost:8774/v2.1/servers/{server_id}/action \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reboot": {"type": "SOFT"}}'

# Delete server
curl -s -X DELETE http://localhost:8774/v2.1/servers/{server_id} \
  -H "X-Auth-Token: $TOKEN"
```

### Flavors

```bash
# List flavors
curl -s http://localhost:8774/v2.1/flavors \
  -H "X-Auth-Token: $TOKEN" | jq

# List flavors (detailed)
curl -s http://localhost:8774/v2.1/flavors/detail \
  -H "X-Auth-Token: $TOKEN" | jq

# Get flavor
curl -s http://localhost:8774/v2.1/flavors/{flavor_id} \
  -H "X-Auth-Token: $TOKEN" | jq
```

### Keypairs

```bash
# List keypairs
curl -s http://localhost:8774/v2.1/os-keypairs \
  -H "X-Auth-Token: $TOKEN" | jq

# Create keypair
curl -s -X POST http://localhost:8774/v2.1/os-keypairs \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"keypair": {"name": "my-key"}}' | jq

# Import keypair
curl -s -X POST http://localhost:8774/v2.1/os-keypairs \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"keypair": {"name": "my-key", "public_key": "ssh-rsa AAAA..."}}' | jq

# Delete keypair
curl -s -X DELETE http://localhost:8774/v2.1/os-keypairs/my-key \
  -H "X-Auth-Token: $TOKEN"
```

## Cinder (Block Storage)

### Volumes

```bash
# List volumes
curl -s "http://localhost:8776/v3/$PROJECT_ID/volumes/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create volume
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/volumes" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "my-volume", "size": 10}}' | jq

# Get volume
curl -s "http://localhost:8776/v3/$PROJECT_ID/volumes/{volume_id}" \
  -H "X-Auth-Token: $TOKEN" | jq

# Update volume
curl -s -X PUT "http://localhost:8776/v3/$PROJECT_ID/volumes/{volume_id}" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume": {"name": "renamed-volume"}}' | jq

# Extend volume
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/volumes/{volume_id}/action" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"os-extend": {"new_size": 20}}'

# Delete volume
curl -s -X DELETE "http://localhost:8776/v3/$PROJECT_ID/volumes/{volume_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Snapshots

```bash
# List snapshots
curl -s "http://localhost:8776/v3/$PROJECT_ID/snapshots/detail" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create snapshot
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/snapshots" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"snapshot": {"name": "my-snapshot", "volume_id": "{volume_id}"}}' | jq

# Delete snapshot
curl -s -X DELETE "http://localhost:8776/v3/$PROJECT_ID/snapshots/{snapshot_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Volume Types

```bash
# List volume types
curl -s "http://localhost:8776/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create volume type
curl -s -X POST "http://localhost:8776/v3/$PROJECT_ID/types" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"volume_type": {"name": "ssd", "description": "SSD storage"}}' | jq
```

## Glance (Image)

### Images

```bash
# List images
curl -s "http://localhost:9292/v2/images" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create image
curl -s -X POST "http://localhost:9292/v2/images" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-image", "container_format": "bare", "disk_format": "qcow2"}' | jq

# Get image
curl -s "http://localhost:9292/v2/images/{image_id}" \
  -H "X-Auth-Token: $TOKEN" | jq

# Update image (JSON Patch)
curl -s -X PATCH "http://localhost:9292/v2/images/{image_id}" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/openstack-images-v2.1-json-patch" \
  -d '[{"op": "replace", "path": "/name", "value": "new-name"}]' | jq

# Upload image data
curl -s -X PUT "http://localhost:9292/v2/images/{image_id}/file" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/path/to/image.qcow2

# Add tag
curl -s -X PUT "http://localhost:9292/v2/images/{image_id}/tags/my-tag" \
  -H "X-Auth-Token: $TOKEN"

# Deactivate image
curl -s -X POST "http://localhost:9292/v2/images/{image_id}/actions/deactivate" \
  -H "X-Auth-Token: $TOKEN"

# Delete image
curl -s -X DELETE "http://localhost:9292/v2/images/{image_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Image Sharing

```bash
# Set visibility to shared
curl -s -X PATCH "http://localhost:9292/v2/images/{image_id}" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/openstack-images-v2.1-json-patch" \
  -d '[{"op": "replace", "path": "/visibility", "value": "shared"}]'

# Add member (share with project)
curl -s -X POST "http://localhost:9292/v2/images/{image_id}/members" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"member": "{project_id}"}' | jq

# List members
curl -s "http://localhost:9292/v2/images/{image_id}/members" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Neutron (Networking)

### Networks

```bash
# List networks
curl -s "http://localhost:9696/v2.0/networks" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create network
curl -s -X POST "http://localhost:9696/v2.0/networks" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"network": {"name": "my-network", "admin_state_up": true}}' | jq

# Get network
curl -s "http://localhost:9696/v2.0/networks/{network_id}" \
  -H "X-Auth-Token: $TOKEN" | jq

# Delete network
curl -s -X DELETE "http://localhost:9696/v2.0/networks/{network_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Sharing a network with another project (RBAC)

```bash
# Share a network with one project
curl -s -X POST "http://localhost:9696/v2.0/rbac-policies" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rbac_policy": {"object_type": "network", "object_id": "{network_id}",
       "target_tenant": "{project_id}", "action": "access_as_shared"}}' | jq

# List the policies on a network. The policy is owned by the network's project,
# not by the admin session that created it.
curl -s "http://localhost:9696/v2.0/rbac-policies?object_id={network_id}" \
  -H "X-Auth-Token: $TOKEN" | jq

# Revoking a share still in use is a 409 until the target project's ports are gone
curl -s -X DELETE "http://localhost:9696/v2.0/rbac-policies/{policy_id}" \
  -H "X-Auth-Token: $TOKEN" | jq
```

The target project may create ports on a network shared this way, but may not
pin `fixed_ips[].ip_address` on it — that is admin-or-network-owner in Neutron
and answers `403`. See
[Tenant Isolation → Network Sharing](./architecture/tenant-isolation.md#network-sharing).

### Subnets

```bash
# List subnets
curl -s "http://localhost:9696/v2.0/subnets" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create subnet
curl -s -X POST "http://localhost:9696/v2.0/subnets" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subnet": {
      "name": "my-subnet",
      "network_id": "{network_id}",
      "ip_version": 4,
      "cidr": "10.0.0.0/24"
    }
  }' | jq

# Delete subnet
curl -s -X DELETE "http://localhost:9696/v2.0/subnets/{subnet_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Ports

```bash
# List ports
curl -s "http://localhost:9696/v2.0/ports" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create port
curl -s -X POST "http://localhost:9696/v2.0/ports" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"port": {"name": "my-port", "network_id": "{network_id}"}}' | jq

# Delete port
curl -s -X DELETE "http://localhost:9696/v2.0/ports/{port_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Routers

```bash
# List routers
curl -s "http://localhost:9696/v2.0/routers" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create router
curl -s -X POST "http://localhost:9696/v2.0/routers" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"router": {"name": "my-router", "admin_state_up": true}}' | jq

# Set external gateway
curl -s -X PUT "http://localhost:9696/v2.0/routers/{router_id}" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"router": {"external_gateway_info": {"network_id": "{external_network_id}"}}}' | jq

# Add router interface
curl -s -X PUT "http://localhost:9696/v2.0/routers/{router_id}/add_router_interface" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subnet_id": "{subnet_id}"}' | jq

# Remove router interface
curl -s -X PUT "http://localhost:9696/v2.0/routers/{router_id}/remove_router_interface" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subnet_id": "{subnet_id}"}' | jq

# Delete router
curl -s -X DELETE "http://localhost:9696/v2.0/routers/{router_id}" \
  -H "X-Auth-Token: $TOKEN"
```

### Floating IPs

```bash
# List floating IPs
curl -s "http://localhost:9696/v2.0/floatingips" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create floating IP
curl -s -X POST "http://localhost:9696/v2.0/floatingips" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"floatingip": {"floating_network_id": "{external_network_id}"}}' | jq

# Associate with port
curl -s -X PUT "http://localhost:9696/v2.0/floatingips/{floatingip_id}" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"floatingip": {"port_id": "{port_id}"}}' | jq

# Delete floating IP
curl -s -X DELETE "http://localhost:9696/v2.0/floatingips/{floatingip_id}" \
  -H "X-Auth-Token: $TOKEN"
```

The create call rejects an unusable target network the way Neutron does, so a
client can tell a configuration mistake from a missing resource:

| Condition | Status | Message |
|-----------|--------|---------|
| Network does not exist | 404 | `External network not found` |
| Network exists but is not external | 400 | `Network <id> is not a valid external network` |
| External network has no IPv4 subnet | 400 | `Network <id> does not contain any IPv4 subnet` |

A network shared to the project through an `access_as_external` RBAC policy counts
as external here, exactly as it does for a router gateway.

The port that holds the address (`device_owner: network:floatingip`) belongs to no
project, as in real Neutron — *"This external port is never exposed to the
project"* — so it does not appear in the tenant's `/v2.0/ports` listing and is only
retrievable with an admin token. The same is true of a router's
`network:router_gateway` port.

### Security Groups

```bash
# List security groups
curl -s "http://localhost:9696/v2.0/security-groups" \
  -H "X-Auth-Token: $TOKEN" | jq

# Create security group
curl -s -X POST "http://localhost:9696/v2.0/security-groups" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"security_group": {"name": "web-servers", "description": "Security group for web servers"}}' | jq

# Create rule (SSH)
curl -s -X POST "http://localhost:9696/v2.0/security-group-rules" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "security_group_rule": {
      "security_group_id": "{security_group_id}",
      "direction": "ingress",
      "protocol": "tcp",
      "port_range_min": 22,
      "port_range_max": 22,
      "remote_ip_prefix": "0.0.0.0/0"
    }
  }' | jq

# Create rule (HTTP)
curl -s -X POST "http://localhost:9696/v2.0/security-group-rules" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "security_group_rule": {
      "security_group_id": "{security_group_id}",
      "direction": "ingress",
      "protocol": "tcp",
      "port_range_min": 80,
      "port_range_max": 80,
      "remote_ip_prefix": "0.0.0.0/0"
    }
  }' | jq

# Delete rule
curl -s -X DELETE "http://localhost:9696/v2.0/security-group-rules/{rule_id}" \
  -H "X-Auth-Token: $TOKEN"

# Delete security group
curl -s -X DELETE "http://localhost:9696/v2.0/security-groups/{security_group_id}" \
  -H "X-Auth-Token: $TOKEN"
```

## Placement (Resource Providers)

```bash
# List resource providers (one seeded provider mirrors the default hypervisor)
curl -s "http://localhost:8778/resource_providers" \
  -H "X-Auth-Token: $TOKEN" | jq

# Pick the first provider's UUID
RP_UUID=$(curl -s "http://localhost:8778/resource_providers" \
  -H "X-Auth-Token: $TOKEN" | jq -r '.resource_providers[0].uuid')

# Inventories: VCPU / MEMORY_MB / DISK_GB capacity, with reserved + allocation_ratio
curl -s "http://localhost:8778/resource_providers/$RP_UUID/inventories" \
  -H "X-Auth-Token: $TOKEN" | jq

# Usages: live consumption, computed from running Nova servers
curl -s "http://localhost:8778/resource_providers/$RP_UUID/usages" \
  -H "X-Auth-Token: $TOKEN" | jq

# Allocation candidates: pre-flight scheduler check. `resources` is comma-joined
# CLASS:amount. `allocation_requests` is non-empty when a provider can place the
# request, and empty when the cloud is full (effective capacity minus usage).
curl -s "http://localhost:8778/allocation_candidates?resources=VCPU:2,MEMORY_MB:2048" \
  -H "X-Auth-Token: $TOKEN" | jq

# A request larger than any provider's effective capacity returns no candidates
curl -s "http://localhost:8778/allocation_candidates?resources=VCPU:1000" \
  -H "X-Auth-Token: $TOKEN" | jq '.allocation_requests'
```

## Limits and Quotas

```bash
# Nova limits
curl -s "http://localhost:8774/v2.1/limits" \
  -H "X-Auth-Token: $TOKEN" | jq

# Cinder limits
curl -s "http://localhost:8776/v3/$PROJECT_ID/limits" \
  -H "X-Auth-Token: $TOKEN" | jq

# Neutron quotas
curl -s "http://localhost:9696/v2.0/quotas/$PROJECT_ID" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Object Storage (Swift)

The account is the `AUTH_<project id>` segment of the storage URL, which is what
the service catalog points a client at.

```bash
ACCOUNT="AUTH_$PROJECT_ID"

# Account metadata, usage totals and quotas
curl -s -I "http://localhost:8080/v1/$ACCOUNT" -H "X-Auth-Token: $TOKEN"

# Set a byte quota. Only a reseller (an admin token here) may write this;
# X-Account-Meta-Quota-Bytes is the obsoleted spelling and is translated.
curl -s -X POST "http://localhost:8080/v1/$ACCOUNT" \
  -H "X-Auth-Token: $TOKEN" -H "X-Account-Quota-Bytes: 10737418240"

# Containers and objects
curl -s -X PUT "http://localhost:8080/v1/$ACCOUNT/backups" -H "X-Auth-Token: $TOKEN"
curl -s -X PUT "http://localhost:8080/v1/$ACCOUNT/backups/dump.tar" \
  -H "X-Auth-Token: $TOKEN" --data-binary @dump.tar
curl -s "http://localhost:8080/v1/$ACCOUNT/backups?format=json" \
  -H "X-Auth-Token: $TOKEN" | jq

# An upload over the quota is refused with 413
```

## Per-volume-type quotas (Cinder)

Cinder derives a quota key per metric for every volume type, so a quota set
carries `gigabytes_<type>`, `volumes_<type>` and `snapshots_<type>` alongside the
totals. A key naming a type that does not exist is a 400.

```bash
curl -s -X PUT "http://localhost:8776/v3/$PROJECT_ID/os-quota-sets/$PROJECT_ID" \
  -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"quota_set": {"gigabytes": 2000, "gigabytes_nvme": 500, "volumes_nvme": 20}}' | jq

# With usage, every key reports limit / in_use / reserved
curl -s "http://localhost:8776/v3/$PROJECT_ID/os-quota-sets/$PROJECT_ID?usage=true" \
  -H "X-Auth-Token: $TOKEN" | jq
```

## Rating (CloudKitty)

```bash
# Summary grouped by project, table format (the default)
curl -s "http://localhost:8889/v2/summary?groupby=project_id" \
  -H "X-Auth-Token: $TOKEN" | jq

# Object format, filtered to one metric
curl -s "http://localhost:8889/v2/summary?response_format=object&filters=type:instance" \
  -H "X-Auth-Token: $TOKEN" | jq

# The individual rating points behind the summary
curl -s "http://localhost:8889/v2/dataframes" -H "X-Auth-Token: $TOKEN" | jq
```

## Federated identity

See [Federated identity (OIDC)](./federation.md) for the full flow. In short:

```bash
# Get an access token from the embedded OpenID Provider
ACCESS_TOKEN=$(curl -s -X POST http://localhost:5556/token \
  -d grant_type=password -d username=alice -d password=password \
  -d client_id=waldur -d client_secret=secret | jq -r .access_token)

# Exchange it for an unscoped Keystone token
curl -s -i -X POST \
  "http://localhost:5000/v3/OS-FEDERATION/identity_providers/keycloak/protocols/openid/auth" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | grep -i x-subject-token

# Discover what it may scope to
curl -s http://localhost:5000/v3/OS-FEDERATION/projects \
  -H "X-Auth-Token: $UNSCOPED_TOKEN" | jq
```

## Project tags

```bash
curl -s -X PUT "http://localhost:5000/v3/projects/$PROJECT_ID/tags/managed-by-agent" \
  -H "X-Auth-Token: $TOKEN"

curl -s "http://localhost:5000/v3/projects?tags=managed-by-agent" \
  -H "X-Auth-Token: $TOKEN" | jq '.projects[].name'
```

## Related Documentation

- [Usage Guide](./usage.md) - General usage instructions
- [Federated identity (OIDC)](./federation.md) - Keystone federation and the embedded provider
- [Scenario Injection](./scenarios.md) - Failure testing
