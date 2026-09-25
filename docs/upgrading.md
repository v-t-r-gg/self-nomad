# Upgrading

Guidance for moving to **1.4.0** (unreleased on `main`). It keeps schema 1,
the 1.0 JSON and MCP contracts, the 1.1 pack format, and the 1.2 TUI.
`v1.3.0` is the tagged workspace-adapter release. Historical notes remain in
[CHANGELOG.md](../CHANGELOG.md). Release notes:
[releases/1.3.0.md](releases/1.3.0.md),
[releases/1.2.0.md](releases/1.2.0.md),
[releases/1.1.1.md](releases/1.1.1.md),
[releases/1.1.0.md](releases/1.1.0.md), and
[releases/1.0.0.md](releases/1.0.0.md).

## Version and schema

| Item | Value |
| --- | --- |
| Package version | `1.4.0` (from `pyproject.toml`, not tagged yet) |
| Repository `schema_version` | **1** (unchanged) |
| Pack format | `self-nomad-pack-v1` |
| Source-tree version sentinel | `0+unknown` when not installed |

No repository format migration is required for schema 1 trees created under
earlier releases. Policy files that omit `limits.maximum_request_bytes` still
receive the 4 MiB default.

From 1.0.0, rebuild specialist packs that used `--include-long-term-memory`.
1.1.0 packs only `memory/PUBLISH.md` for that flag, and `pack --check` of a
personal archive requires `--profile personal`.

1.1.1 does not change the pack format. `pack --check` and `install` now reject
a sidecar whose self id, name, description, or skill list does not match the
archived tree. Tag `v1.1.0` does not include that check.

## Operator loop

Apply no longer requires switching the target branch away. A **clean**
checked-out `main` is refreshed after apply. A **dirty** worktree is refused.

`init --git` writes the initial commit.

## Snapshots

```bash
self-nomad --repo ./agent pack --out ./agent.snpack
self-nomad install ./agent.snpack --to ./copy
```

Do not publish a live Git clone. Use `pack`.

## MCP

Still optional (`self-nomad[mcp]`), still seven tools, still no approve/apply.

## Compatibility

[compatibility.md](compatibility.md) is the 1.0 contract freeze.

## Python versions

Supported: 3.11, 3.12, 3.13.
