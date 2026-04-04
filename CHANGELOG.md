# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-04-04

### Changed
- Remove manual name/ID override from `AnovaNanoSwitch`, letting Home Assistant generate them dynamically (#24)

### Breaking Changes
- The `Cooking` switch entity ID will change after this update. Existing users will see a duplicate switch entity. To resolve: delete the old entity and rename the new one if needed for dashboards or automations.

## [0.7.2] - 2025-06-20

### Added
- CLAUDE.md file for improved development workflow
- Release process documentation

### Fixed
- Update pyanova nano for protobuf conflict (#20)
- Fix target temp bounds degrees fahrenheit (#18)
- Fix domain typo in my link (#16)

### Changed
- Update name in manifests (#15)
- Version consistency across all project files

## [0.7.1] - 2025-04-29

### Changed
- Update readme (#12)
- Update to pyanova-nano==0.2.3 (#11)

## [0.7.0] - 2025-04-20

### Technical
- Various improvements and updates

## [0.6.2] - 2024-11-12

### Changed
- Updated pyanova-nano dependency

## [0.6.1] - 2024-10-16

### Fixed
- Match max cooking time to device (#10)

## [0.6.0] - 2024-10-09

### Fixed
- Fix unit conversion (#9)
- Fix unit tests (#8)
- Fix esphome bt proxy compatibility (#6)

### Changed
- Bump minimum HA version to 2024.10.0
- Switch to python 3.12 & uv & fix tests (#4)
- Fix manifest.json and lint failures (#3)

### Technical
- Various dependency updates and build improvements

## Earlier Versions

For changes prior to 0.6.0, please see the [commit history](https://github.com/mcolyer/home-assistant-anova-nano/commits/main).