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

## Runtime adapters

Adapters return typed detection and transfer plans containing explicit mapping
fidelity, actions, conflicts, and exclusions. Import materialization writes to
local staging and becomes a normal Git proposal. Restore previews by default;
confirmed application rechecks target hashes, copies replaced content to XDG
state, writes regular files atomically, and verifies resulting tree digests.

Hermes manages `SOUL.md`, bounded `memories/MEMORY.md` and
`memories/USER.md`, and profile-local skills. `.env`, `state.db`, sessions, and
configuration remain excluded or runtime-owned. OpenClaw manages only its
workspace bootstrap files, memory, and workspace skills; its state directory
is never an adapter input. `BOOTSTRAP.md` remains runtime-owned.

Restore builds and verifies a complete sibling runtime tree before changing the
live path. It backs up affected artifacts, renames the original runtime aside,
atomically installs the staged directory, verifies live hashes, and rolls the
original directory back on any failure. Proposal application refuses a target
branch checked out in any worktree; users must detach or switch that checkout
before applying, preventing ref/index/worktree divergence.
