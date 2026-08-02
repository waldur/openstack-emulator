# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

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
