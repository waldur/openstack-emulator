# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.6.0] - 2026-09-17

### Added
- Add IPv6 and dual-stack emulation to Neutron, with one address allocated per family for ports and router gateways on dual-stack networks
- Accept `ipv6_ra_mode` and `ipv6_address_mode` on subnet create, validate them as Neutron does, and refuse changes to them after creation
- Derive a port's address from the subnet prefix and its MAC on SLAAC and stateless DHCPv6 subnets, and refuse a caller-chosen address there
- Accept `fixed_ips` and `allowed_address_pairs` on port update, replacing the whole list as Neutron does
- Refuse allowed address pairs that name or cover a multicast range
- Allocate Octavia VIPs from their VIP subnet, so an IPv6 VIP subnet yields an IPv6 VIP
- Carry `ip_version` and the IPv6 address modes through preset subnets

### Fixed
- Fix IPv6 address allocation so it computes addresses directly instead of listing every address in the prefix, which made IPv6 subnets unusable
- Fix IPv6 subnet gateway and allocation pool derivation, which parsed the prefix as IPv4
- Fix floating IPs to be allocated only from IPv4 subnets and associated with a port's IPv4 fixed IP
- Fix server address `version`, which was always reported as 4
- Fix `0.0.0.0/0` being refused as an allowed address pair
- Return Neutron's own error messages for refused allowed address pairs, invalid IPv6 address modes and fixed addresses on auto-address subnets

## [0.5.0] - 2026-09-10

### Fixed
- Fix Neutron router deletion so a missing router, or one owned by another project, returns 404 `RouterNotFound` instead of a 409
- Fix Neutron router deletion to return 409 `RouterInUse` ("Router <id> still has ports") when the router still has interfaces attached
- Fix router deletion being blocked by an external gateway port, which is now released along with the router, as Neutron does

## [0.4.4] - 2026-09-08

### Added
- Serve the Nova server metadata sub-resource
- Publish a chart landing page alongside the Helm repository index

### Changed
- Roll the deployment pod when the preset ConfigMap changes
- Wire the dependency licence gate into CI

### Fixed
- Honour the `tenant_id`/`project_id` filter when listing Neutron routers
- Fix two latent faults in the chart publish job

## [0.4.3] - 2026-08-17

### Fixed
- Return Neutron API errors in Neutron's own error envelope

## [0.4.2] - 2026-08-03

### Added
- Allocate an external fixed IP on the gateway port when a router gateway is set
- Allocate floating IPs from the external subnet's allocation pool

### Changed
- Pin the ids of the seeded default networks so they are deterministic across restarts
- Match Neutron's error contract for floating IP and router gateway failures
- Update the docs to match the emulator's actual behaviour

## [0.4.1] - 2026-08-02

### Fixed
- Honour domain identifiers given by name when scoping authentication and identity resources
- Match Neutron's RBAC rules for shared networks

## [0.4.0] - 2026-08-02

### Added
- Add Swift object storage service with container and object APIs
- Add OIDC federated identity with an embedded OpenID Provider
- Add CloudKitty rating service
- Add a real token authorization model requiring role assignments for scoped tokens
- Show Swift, federation and OpenID Provider state in the status dashboard

### Changed
- Improve quota fidelity across services
- Bind ports when a server is booted
- Pin ruff and mypy so CI and local environments behave identically

### Fixed
- Answer a rejected token with 401 instead of 404
- Apply the port offset to the status dashboard health checks and service catalog

## [0.3.0] - 2026-07-31

### Added
- Log injected scenario failures and report which records are dropped during database load

### Changed
- Rework database persistence so state is restored across restarts
- Isolate save failures per record so one bad record no longer halts all persistence

### Fixed
- Connect failure injection to the requests it is meant to affect

## [0.2.4] - 2026-07-28

### Fixed
- Validate port ownership in Nova interface attach

## [0.2.3] - 2026-07-08

### Added
- Add Placement `/allocation_candidates` endpoint

## [0.2.2] - 2026-07-07

### Added
- Allow admin users to access servers across all projects

## [0.2.1] - 2026-06-29

### Changed
- Version code, Docker image, and Helm chart together from a single release
- Stop auto-pushing releases to a hard-coded remote; push to the explicit upstream and print the push command instead

### Fixed
- Fix changelog insertion on an empty changelog and make the helm test version-independent

## [0.2.0] - 2026-06-29

### Added
- Version code, Docker image, and Helm chart together from a single release

### Fixed
- Fix changelog insertion when the changelog is empty
- Make Helm test version-independent
- Push release tag to GitLab explicitly instead of the default remote
