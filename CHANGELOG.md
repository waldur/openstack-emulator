# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Accept `ipv6_ra_mode` and `ipv6_address_mode` on subnet create, and refuse a mode on an IPv4 subnet, an unknown mode value, or SLAAC/stateless without a /64
- Refuse changing either address mode after a subnet is created, as Neutron's read-only attributes do
- Derive a port's address from the prefix and its MAC on SLAAC and stateless DHCPv6 subnets, and refuse a caller-chosen address there
- Accept `fixed_ips` and `allowed_address_pairs` on port update, replacing the whole list as Neutron does, so a re-sent entry counts as unchanged
- Refuse an allowed address pair that names or covers a multicast range (which is why `::/0` is refused)
- Allocate one address per family, so a port and a router gateway on a dual-stack network hold both
- Allocate an Octavia VIP from its VIP subnet, so an IPv6 VIP subnet yields an IPv6 VIP
- Carry `ip_version` and the IPv6 address modes through preset subnets

### Fixed
- Accept `0.0.0.0/0` as an allowed address pair, which Neutron exempts from the multicast check before it runs, while still refusing `::/0` because it collapses onto `ff00::/8`
- Report Neutron's own message for a refused allowed address pair, an invalid IPv6 address mode and a fixed address on an auto-address subnet, rather than wording of our own — including the API layer's "Invalid input for ... Reason: ..." wrapper, which the first two reach through an attribute validator
- Allocate IPv6 addresses arithmetically instead of enumerating a prefix, which made an IPv6 subnet unusable
- Derive an IPv6 subnet's gateway and allocation pool from its prefix instead of parsing it as IPv4
- Allocate floating IPs only from IPv4 subnets, and associate one with a port's IPv4 fixed IP rather than its first
- Report a server address's `version` from the address itself instead of always 4

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
