# Upgrading

Guidance for moving from **0.1.0rc1** toward current **0.2.0.dev0** development
checkouts. Historical release notes remain in [CHANGELOG.md](../CHANGELOG.md).

## Version and schema

| Item | Value |
| --- | --- |
| Package development version | `0.2.0.dev0` (from `pyproject.toml`) |
| Repository `schema_version` | **1** (unchanged) |
| Source-tree version sentinel | `0+unknown` when not installed |

No repository format migration is required for schema 1 trees created under the RC.

## Private state layout

Pre-RC development used longer path segments under the platform state directory.
RC and current builds use compact segments:

```text
r/<repo-key>/p   # proposal records
r/<repo-key>/w   # worktrees
```

**Pre-RC pending proposal records are not discovered automatically.** Finish or
discard in-flight drafts before upgrading when possible, or move records
manually if recovery is required.

## New optional MCP dependency

```bash
pip install 'self-nomad[mcp]'
self-nomad-mcp --repo /absolute/path/to/agent-self
```

Base installs omit the MCP SDK. The `self-nomad-mcp` console script exists in
the package but exits with an install hint when the extra is missing.

## Intake receipts

0.2 development adds durable intake receipts (idempotency, frozen base commit,
crash recovery). Receipts live in private platform state, not in the portable
Git tree. Unfinished intake submissions may leave recoverable pending receipts;
safe approach: preview-only until ready, then submit once with a stable
`request_id`.

## Unfinished proposals

Before upgrading tooling:

1. List pending proposals (`review` / status tooling).
2. Apply, reject, or abandon in-flight work.
3. Ensure no critical work depends solely on pre-RC state paths.

## Python versions

Supported: 3.11, 3.12, 3.13.

## Related

- [Releasing](releasing.md) for maintainers cutting a future 0.2 release
- [Troubleshooting](troubleshooting.md)
