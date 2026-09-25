# Threat model

## Protected assets

- Durable agent content (identity, memory, skills)
- Repository history and proposal audit records
- Runtime targets during restore
- Private operational state (receipts, worktrees) on the operator machine
- Credentials and sessions (by **exclusion** from the product boundary)

## Trust boundaries

| Trusted | Untrusted |
| --- | --- |
| Operator who runs CLI / configures MCP | Agent-submitted intake JSON |
| Local Git binary and configured filters | Repository content as data |
| Host that spawns `self-nomad-mcp` | MCP tool arguments |
| Explicit runtime roots for adapters | Runtime trees as untrusted files |

## Attacker-controlled inputs

Manifest paths, repository files, intake requests, adapter runtime trees,
MCP tool payloads, and third-party snapshot packs (`install` / `pack --check`).

## Enforced invariants

- Path traversal and escaping symlink rejection
- Safe YAML load
- Policy size limits
- Atomic file writes
- No execution of repository-provided tests/scripts as product behavior
- Managed Git: hooks disabled (`core.hooksPath` null device), no prompts
- Proposal validation binds complete tree + declared diff
- Apply compare-and-swap plus reset of a clean checked-out worktree;
  dirty worktrees are refused
- Pack install extracts to staging and validates before writing the destination
  (digest match, no `.git`, no links, no path escape, fail-closed secrets)
- Restore: stage, verify, backup, swap, verify, rollback
- Adapters report unmapped classes; they never run Git or approve

## Proposal and approval guarantees

Approval records an identifier without authenticating the human. Tree binding
and stale detection still apply. MCP never exposes approve/apply.

## Intake and MCP boundaries

- Inline UTF-8 only; no caller content paths
- Fixed public error messages (no Git stderr or path leaks in MCP envelopes)
- Seven native tools only; fixed absolute `--repo`
- Structured next actions never imply MCP can approve/apply

## Adapter exclusions

Credentials, sessions, databases, Hermes `.env` / `state.db`, OpenClaw state
directory, and runtime-owned bootstrap files are excluded from portability.

## Trusted Git filters

Clean/smudge/process filters are trusted local infrastructure. Approval binds
resulting tree bytes, not the filter program.

## Residual risks

- Git history retains deleted content (use `pack`, not a live clone)
- Structural validation is not behavioral safety of agent instructions
- Secret scanning is not general DLP
- Compromised host can point MCP at any local path the operator allows
- Agents with shell outside MCP can bypass the MCP surface
- Apply after `update-ref` and before `reset --hard` can leave a moved ref
  with a stale worktree if the process dies (recover with `git reset --hard HEAD`)

## Explicit product exclusions

No LLM calls, no remote push from apply, no credential vaults, no automatic
approval, no remote MCP transports, no marketplace hosting or remote package
index in this product ([ADR 0007](decisions/0007-publishable-package-profile.md)).
