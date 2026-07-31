# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed
- Make failure injection work at all. The scenarios API and the Status UI enabled scenarios on one manager instance while the injection middleware read a different one, so an "enabled" scenario never affected a request — the API reported it active and the stats reported zero injections. Broken since the single-process refactor in December 2025.
- Restore delay and timeout injection, including delay-only load scenarios and injected 504s, which the replacement manager never implemented.

### Removed
- `emulator/core/shared_state.py` and `emulator/core/simple_scenarios.py`, along with `ScenarioManager.sync_from_shared_state()`. These synchronised scenario state through `/tmp/openstack-emulator-scenarios.json` for a multi-process layout that no longer exists; nothing read the file.

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
