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

Manifest paths, repository files, intake requests, adapter runtime trees, and
MCP tool payloads.

## Enforced invariants

- Path traversal and escaping symlink rejection
- Safe YAML load
- Policy size limits
- Atomic file writes
- No execution of repository-provided tests/scripts as product behavior
- Managed Git: hooks disabled (`core.hooksPath` null device), no prompts
- Proposal validation binds complete tree + declared diff
- Apply refuses checked-out target branches
- Restore: stage, verify, backup, swap, verify, rollback

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

- Git history retains deleted content
- Structural validation is not behavioral safety of agent instructions
- Secret scanning is not general DLP
- Compromised host can point MCP at any local path the operator allows
- Agents with shell outside MCP can bypass the MCP surface

## Explicit product exclusions

No LLM calls, no remote push from apply, no credential vaults, no automatic
approval, no remote MCP transports in the current slice.
