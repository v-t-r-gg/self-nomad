# Architecture

The CLI translates terminal input and structured results. Application services
orchestrate use cases. Domain schemas, policy, validation, adapters, and the
self repository depend only on lower-level filesystem and Git infrastructure.
Adapters never run Git or decide authorization; the policy layer never performs
runtime writes.

The initial implementation covers repository initialization and deterministic
validation.

## Proposal transaction

Proposal metadata and worktrees live under the platform state directory, keyed
by a hash of the repository path. A proposal records its target ref and base
commit, then materializes typed add, replace, or delete operations on a
dedicated `self-nomad/proposal/<uuid>` branch and worktree. The active checkout
is not switched or written during proposal creation.

Validation records a digest of authoritative content. Approval is a separate
state transition. Application reacquires the repository lock, checks the target
ref and content digest, commits a redacted audit record, and advances the target
with `git update-ref <ref> <new> <expected-old>`. A moved target becomes stale;
there is no implicit merge or rebase. No application operation pushes a remote.
