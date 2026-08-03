# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

### Security

## [0.1.0rc1] - 2026-08-03

First public release candidate of the safety-hardened deterministic core.

### Added

- Typed Python 3.11+ package with Hatchling builds (wheel and sdist).
- Typer CLI (`self-nomad`) with stable JSON envelopes (`schema_version`,
  `command`, `ok`, `result`, `warnings`, `errors`) and `--version`.
- Git-isolated proposals whose validation and approval bind the full tree and
  declared diff.
- Transactional restore with adjacent staging, verification, atomic swap, and
  automatic rollback on failure.
- Built-in Hermes and OpenClaw adapters with fidelity and exclusion reporting.
- Single public version source (`0.1.0rc1`) via package metadata with a narrow
  source-tree fallback.
- Cross-platform CI: Linux quality job; Python 3.11–3.13 tests on Ubuntu;
  Python 3.13 compatibility on macOS and Windows; distribution job that builds
  once and smoke-tests installed wheel and sdist artifacts.
- Release smoke harness (`scripts/release_smoke.py`) for non-editable installs.
- Coverage configuration that measures CLI paths and enforces a floor.
- Release documentation: this changelog, `docs/releasing.md`, and expanded
  README / CONTRIBUTING guidance.

### Security

- Managed Git commands disable repository and global hooks (`core.hooksPath`
  set to a platform-appropriate null device).
- Credentials, sessions, databases, and runtime-owned state stay outside
  migration; secret scanning catches high-confidence patterns only.
- Configured Git clean/smudge/process filters remain trusted local
  infrastructure and are not treated as an untrusted input boundary.

### Known limitations (release candidate)

- Target branches must be detached or switched away before proposal application.
- Secret scanning is not general-purpose data-loss prevention.
- Preview-first adapter flow: import/restore plan by default; `--yes` confirms
  the displayed class of mutation only.

[Unreleased]: https://github.com/v-t-r-gg/self-nomad/compare/v0.1.0rc1...HEAD
[0.1.0rc1]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v0.1.0rc1
