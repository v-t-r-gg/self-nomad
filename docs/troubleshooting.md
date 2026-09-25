# Troubleshooting

## Repository validation failures

- Run `self-nomad --repo PATH --json validate --strict` and inspect `errors` / findings.
- Check portable paths (no `..`, absolute paths, backslashes, or escaping symlinks).
- Oversized files exceed `limits.maximum_file_bytes` (default 1 MiB).
- Secret-like patterns in authoritative content produce findings when scanning is enabled.

## Path and symlink rejection

Manifest and operation paths must be repository-relative POSIX paths. Symlinks
as artifact sources/targets or escaping the repository are rejected.

## Proposal becomes stale

Causes: target branch moved, worktree dirtied after validation/approval, content
digest mismatch. Create a new proposal from the current tip; stale proposals are
not auto-merged.

## Target worktree is dirty

```text
target worktree is dirty; commit, stash, or discard local changes before apply
```

Apply refreshes a **clean** checked-out branch. Commit, stash, or discard
local edits, then retry. A worktree that is not on the target branch is left
alone; only the ref moves.

## Intake ID conflict

`INTAKE_ID_CONFLICT`: same `request_id` with a different payload digest. Choose
a new `request_id` or resubmit the exact prior payload for idempotent reuse.

## Intake target moved

`INTAKE_TARGET_MOVED`: frozen base commit no longer matches the target tip.
Preview again and submit a new request (new id if the payload also changed).

## Restore rollback

On failure after swap, self-nomad attempts to restore the pre-swap directory
from backup under platform state. If rollback fails, the CLI surfaces
recovery-required errors — do not delete state until the tree is understood.

## Runtime detection ambiguity

Multiple Hermes profiles may match. Pass `--path` / `--from` / `--to` explicitly.
OpenClaw uses the workspace directory only (never the state directory).

## Missing MCP extra

```text
install with: pip install 'self-nomad[mcp]'
```

Exit code 2, empty stdout. Base CLI continues to work without the extra.

## MCP host cannot see tools or schema

- Confirm absolute `--repo` and absolute `command` path to `self-nomad-mcp`.
- OpenClaw: include seven `self_nomad_*` tools **and** `resources_list` /
  `resources_read` in `toolFilter.include`.
- Hermes: `tools.resources: true` and `/reload-mcp` after config edits.
- Run host doctor/probe commands from [mcp-openclaw.md](mcp-openclaw.md) /
  [mcp-hermes.md](mcp-hermes.md).

## Windows path and Git issues

- Prefer short repository roots when possible; state uses compact hashes.
- Ensure Git for Windows is on `PATH`.
- Use absolute paths for MCP `--repo`.

## Locating private application state

Platformdirs / XDG state home, under a `self-nomad` application directory with
`r/<repo-key>/` segments for proposals and worktrees. Treat as **local control
plane**, not portable self content. Do not commit it into the self repository.
