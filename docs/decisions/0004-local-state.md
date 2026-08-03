# ADR 0004: Keep control state outside portable content

Status: accepted

Machine-specific configuration uses the platform configuration directory or
ignored `.self-nomad.local.yaml`. Locks, proposal worktrees, staging data, and
recovery backups will use the platform state directory keyed by a repository
hash. They are never portable content.

As of 0.1.0rc1 the on-disk layout under the state directory is compact
(`r/<16-hex-repo-key>/p` for proposal JSON, `r/<16-hex-repo-key>/w` for
worktrees). Pre-RC development layouts used longer path segments
(`repos/.../proposals`, `repos/.../worktrees`) and are not auto-migrated.

