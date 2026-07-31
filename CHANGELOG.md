# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed
- Restore enum-typed fields correctly when loading a persisted database. Network, port and router statuses came back as plain strings, so `GET /v2.0/networks` returned 500 on the first call after every restart.
- Rework persistence so state actually survives a restart: 70 collections are saved instead of 17. Security group rules, volume attachments, server network interfaces, quotas, Octavia and Placement state, router static routes and a network's subnet list were all silently discarded.
- Stop a single malformed record from discarding the rest of the database and then being overwritten by the next auto-save. Bad records are skipped and logged, and the original file is preserved as `<path>.corrupt-<timestamp>`.
- Write the persistence file atomically, so an interrupted save cannot truncate it.
- Keep the floating-IP counter across restarts; it reset to 1 while allocated addresses persisted, handing out duplicates.
- Keep the default project/user/role ids across restarts; they were regenerated while the objects they referred to were loaded from disk.
- Persist the default security group when `--auto-save` is enabled.
- Do not grant admin privileges to a token scoped to an unknown project id. The project name defaulted to `admin`, which the emulator treats as privileged, so such a session got cross-tenant access.
- Return the OpenStack error body for unmatched routes; only `fastapi.HTTPException` was handled, so those 404s used a different shape from every other error.

### Added
- Access log naming the service and port that handled each request. All services share one process and one stdout, and uvicorn's access log identified neither, which made production 404s unattributable.
- Persistence schema versioning with a compatibility path for files written by earlier versions; they are read as-is and upgraded on the next save.
- Tests for `GET /v2.1/servers/{id}/os-security-groups`, which had none.

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
