# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

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
