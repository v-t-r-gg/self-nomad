# ADR 0004: Keep control state outside portable content

Status: accepted

Machine-specific configuration uses the platform configuration directory or
ignored `.self-nomad.local.yaml`. Locks, proposal worktrees, staging data, and
recovery backups will use the platform state directory keyed by a repository
hash. They are never portable content.

