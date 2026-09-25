# Compatibility (1.0)

This document is the 1.0 contract freeze. Breaking these surfaces requires a
major version.

## Repository schema

- `self-nomad.yaml` `schema_version` **1** remains the only supported value.
- Additive sidecars (`self-nomad.pack.json`) must not be required to load a
  schema 1 tree.
- Unknown manifest fields stay forbidden (`extra: forbid`).

## CLI and JSON envelopes

Human output may gain panels and banners. Machine output is `--json`:

```text
schema_version, command, ok, result, warnings, errors
```

- `schema_version` for CLI envelopes is **1**.
- New result keys may be added; existing keys keep their meaning.
- `--interactive` remains incompatible with `--json`.
- `NO_COLOR` / non-TTY hide the wordmark; `--json` never prints it.

## MCP

- Optional extra `self-nomad[mcp]`.
- Stdio only, one absolute `--repo` per process.
- Exactly the documented seven tools. No approve, apply, import, restore,
  pack, or install tools.

## Snapshot packs

- Format id: `self-nomad-pack-v1`.
- Gzip tar, no `.git`, no links, no path escape.
- Specialist profile is the pack default.
- `pack --check` and `install` validate `--strict` and compare
  `content_digest` before trusting the tree.
- 1.1.0 keeps this format id. It adds fail-closed checks, LF text
  normalization, `packer_version`, and a specialist-only `memory/PUBLISH.md`
  allow-list. It does not add hub commands or a second pack format.
  1.1.1 rejects a sidecar whose self id, name, description, or skill names
  disagree with the archived tree. See [snapshot.md](snapshot.md).

## Adapters

- Built-in: `hermes`, `openclaw`.
- `example-files` is a kit sample and is not registered.
- Plans must list unmapped classes instead of dropping them.
- Adapters do not run Git and do not approve proposals.

## Apply

- Compare-and-swap on the target ref (ADR 0008).
- Clean checked-out worktrees are reset to the applied commit.
- Dirty worktrees are refused.

## Python

Supported: 3.11, 3.12, 3.13. Public entry: `SelfNomad` and the documented
methods on `docs/python-api.md`.
