# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Swift object storage service on port 8080, including the account_quotas
  behaviour: reseller-only quota writes, readable by anyone, and 413 on an
  upload that would exceed the limit
- Embedded OpenID Provider on port 5556 issuing RS256 tokens, and Keystone
  OS-FEDERATION support: protocols, the bearer-token auth endpoint, an attribute
  mapping engine, project and domain discovery, and service providers
- CloudKitty rating service on port 8889 with v2 summary and dataframes derived
  from the emulated servers and volumes
- Keystone project tags, the /tags sub-resource, and tag-based project filters
- Per-volume-type Cinder quotas, quota classes for Cinder and Nova, and the
  application_credential authentication method
- A waldur-site-agent preset covering a managed domain, per-volume-type quotas,
  object storage and a working federated login

### Changed
- **Breaking.** Scoping a token now requires a real role assignment, as in
  Keystone: `TokenModel.mint` runs `_validate_project_scope`, which rejects a
  project-scoped token that would carry no roles. The emulator previously
  issued one and invented an `admin` role. A client scoping to a project it was
  never granted now gets 401 instead of a usable token. Grant the role the way
  an operator would (`openstack role add --project P --user U member`), or use
  the `grant_scope` helper in `tests/conftest.py`
- **Breaking.** An unrecognised user name no longer resolves to the seeded
  admin's identity. It used to inherit the admin's role assignments, so any
  name at all could scope wherever the admin could. Unknown names now get a
  stable identity of their own, derived from the name, holding no assignments
- Resolve token privilege from a real admin role assignment or the admin
  project instead of inferring it from the project name, so the default-role
  fallback for users with no assignments no longer confers access
- Nova and Cinder now require all_tenants to list across projects, matching the
  upstream services: a project_id filter alone never crosses a boundary
- Nova and Cinder detailed quota sets derive their keys from the quota model
  rather than a fixed list

### Fixed
- Preset users are created in their project's domain rather than always in the
  default one
- `--service=placement` is accepted by the CLI

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
