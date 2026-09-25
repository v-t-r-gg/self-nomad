# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-09-25

### Added

- `agents-md` workspace adapter. `AGENTS.md` maps to instructions as adapted. `.env` and vendor state directories stay excluded. A README-only tree is not a candidate.
- `claude-code` adapter. `CLAUDE.md` wins over `AGENTS.md`. The files are not merged. `AGENTS.md` is the fallback only when `CLAUDE.md` is absent.

## [1.2.0] - 2026-09-25

### Added

- Optional `self-nomad[tui]` extra: `self-nomad tui` is a keyboard-first operator loop (detect, import preview, review, apply, pack, check, install, restore) over the existing services. The core wheel does not depend on Textual. `--json` never opens the TUI. Review does not apply. No hub client.

## [1.1.1] - 2026-09-25

Patch on the 1.1.0 pack contract. Tag `v1.1.0` is unchanged.

### Security

- `pack --check` and `install` recompute `self.id`, `self.name`, `self.description`, and skill names from the archived tree and reject a sidecar that disagrees. `content_digest` does not cover the sidecar, so rewriting those fields is not a valid pack.

## [1.1.0] - 2026-09-25

Compatible pack-contract release. Schema 1, JSON envelopes, and the seven MCP
tools are unchanged.

### Added

- Pack sidecar JSON Schema (`self-nomad-pack-v1`) and `packer_version` on `self-nomad.pack.json`.
- `pack --check --json` reports profile, omitted classes, content digest, skill names, and packer version.
- `pack --list` reads the sidecar and member names without extracting the tree.
- Specialist `--include-long-term-memory` packs only `memory/PUBLISH.md`. `init` writes that stub. `memory/MEMORY.md` is not a specialist member.
- Archive member, count, and uncompressed-size caps. UTF-8 text is stored with LF newlines so `content_digest` does not depend on the working tree's newline style.
- Operator acceptance covers pack, check, install, and restore into Hermes and OpenClaw from an installed wheel.
- [docs/snapshot.md](docs/snapshot.md).

### Security

- `pack --check` and `install` fail closed on path escape, planted `.git`, symlinks, secret hits, policy oversize, digest mismatch, and a specialist archive that still contains `identity/user.md` or `memory/daily/*`.

## [1.0.0] - 2026-08-17

First stable release. Schema 1, CLI `--json` envelopes, and the seven-tool
MCP surface are compatibility promises. See [compatibility.md](docs/compatibility.md).

### Added

- Human CLI identity: ASCII wordmark, `about`, and Rich panels/tables for
  status, validate, review, intake, and adapter plans. `--json` envelopes are
  unchanged. Banner respects TTY/`NO_COLOR`/`SELF_NOMAD_BANNER`.
- Proposal review shows a unified diff. `--interactive` can approve or reject
  from that surface and never applies.
- `proposals` lists local records; `log` lists applied `self-nomad(audit):`
  commits from Git. `init --git` writes the initial commit.
- Apply refreshes a clean checked-out target (ADR 0008) and refuses a dirty
  worktree.
- `pack` writes a history-free snapshot (specialist vs personal) plus
  `self-nomad.pack.json`. `pack --check` verifies the archive.
- `install` unpacks a pack into a new repo only after staging validation
  (digest, no Git history, no links, fail-closed secrets).
- Adapter kit (`self_nomad.adapters.kit`) and `ExampleFilesAdapter` sample
  (not registered). Hermes and OpenClaw always report unmapped classes.
- Contract tests under `tests/adapters/`.

### Changed

- Packaging classifier is Production/Stable.

## [0.2.0rc1] - 2026-08-16

Operator-acceptance release candidate for the 0.2 intake and MCP slice.

### Added

- Agent-facing proposal intake: strict `ProposalRequest` v1, preview/submit
  service, CLI `intake`, JSON Schema, and frozen-base idempotent receipts with
  crash recovery and target-commit preflight.
- Policy limit `limits.maximum_request_bytes` (default 4 MiB). Existing schema 1
  policy files omit the field and receive the default.
- Optional bounded local MCP server (`self-nomad-mcp`) behind
  `self-nomad[mcp]` (official Python MCP SDK v2): seven native tools
  (repository status/validate, intake preview/submit, proposal list/get/validate),
  packaged ProposalRequest schema resource, OpenClaw/Hermes host examples,
  structured capability-aware next actions, and installed-artifact MCP smoke
  (`scripts/mcp_smoke.py`).
- Documentation overhaul: docs index, getting started, CLI reference, Python
  API, runtime portability, troubleshooting, upgrading, documentation checker
  (`scripts/check_docs.py`), and end-to-end intake example.
- Product-boundary ADR 0007 (standalone local CLI; a future registry consumes
  validation and snapshot import/export) plus [docs/ecosystem.md](docs/ecosystem.md).
- Clean rebuild helper (`scripts/build_release.py`), `SHA256SUMS` write/verify
  (`scripts/checksums.py`), optional GPG detach-sign, and operator-acceptance
  harness (`scripts/operator_acceptance.py`).
- Frozen first-RC schema fixture and upgrade-path tests.
- GitHub tag workflow that rebuilds artifacts, attests provenance, and opens a
  pre-release with wheel, sdist, and checksums.

### Changed

- Base release smoke asserts the MCP extra is absent and `self-nomad-mcp`
  prints a concise install instruction.
- Releasing documentation is version-agnostic (derives version from
  `pyproject.toml` / artifacts).

### Fixed

- MCP error paths no longer reflect caller-controlled property names; residual
  SDK tool errors map to internal envelopes after argument validation.

### Security

- Intake rejects invalid UTF-8, control characters, path escape, secrets in
  content/provenance, and caller-supplied content paths.
- MCP surface is a closed allow-list (no approve/apply/import/restore tools),
  requires a fixed absolute `--repo`, keeps protocol traffic on stdout and
  diagnostics on stderr, redacts staging paths and inline content, and uses
  fixed public error messages (no raw Git stderr or exception `repr`).

### Known limitations (release candidate)

- Target branches must be detached or switched away before proposal application.
- Secret scanning is not general-purpose data-loss prevention.
- Preview-first adapter flow: import/restore plan by default; `--yes` confirms
  the displayed class of mutation only.
- Snapshot export/import for a public registry is not in this release.
- GitHub Artifact Attestations are produced on tagged releases; local rebuilds
  write `SHA256SUMS` and sign with GPG only when a key is configured.

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
- Single public version source via package metadata; uninstalled source trees
  report the sentinel `0+unknown` (not a hard-coded release version).
- Cross-platform CI: Linux quality job; Python 3.11–3.13 tests on Ubuntu;
  Python 3.13 compatibility on macOS and Windows; distribution job that builds
  once and smoke-tests installed wheel and sdist artifacts.
- Release smoke harness (`scripts/release_smoke.py`) for non-editable installs
  (network used for pip bootstrap and runtime dependency resolve).
- Coverage configuration that measures CLI paths and enforces a floor.
- Release documentation: this changelog, `docs/releasing.md`, and expanded
  README / CONTRIBUTING guidance.
- Proposal content remains UTF-8: application validates UTF-8 then writes the
  original bytes so CRLF and other valid sequences keep hash fidelity without
  accepting arbitrary binary payloads.

### Changed

- Local proposal state under the platform state directory uses compact path
  segments (`r/<repo-key>/p`, `r/<repo-key>/w`) instead of the longer pre-RC
  layout (`repos/<key>/proposals`, `repos/<key>/worktrees`). **Pre-RC pending
  proposal records written under the former XDG/layout paths are not discovered
  automatically.** This is acceptable for the first public RC; development users
  with in-flight draft proposals should finish or discard them before upgrading,
  or move records manually if recovery is required.

### Security

- Managed Git commands disable repository and global hooks (`core.hooksPath`
  set to a platform-appropriate null device).
- Credentials, sessions, databases, and runtime-owned state stay outside
  migration; secret scanning catches high-confidence patterns only.
- Configured Git clean/smudge/process filters remain trusted local
  infrastructure and are not treated as an untrusted input boundary.
- Proposal content sources must be valid UTF-8; invalid encodings are rejected.

### Known limitations (release candidate)

- Target branches must be detached or switched away before proposal application.
- Secret scanning is not general-purpose data-loss prevention.
- Preview-first adapter flow: import/restore plan by default; `--yes` confirms
  the displayed class of mutation only.
- Compact local-state layout is not migrated from pre-RC development checkouts.

[Unreleased]: https://github.com/v-t-r-gg/self-nomad/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v1.3.0
[1.2.0]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v1.2.0
[1.1.1]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v1.1.1
[1.1.0]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v1.1.0
[1.0.0]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v1.0.0
[0.2.0rc1]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v0.2.0rc1
[0.1.0rc1]: https://github.com/v-t-r-gg/self-nomad/releases/tag/v0.1.0rc1
