# ADR 0008: Apply on a clean checked-out target

Status: accepted

## Context

Apply used `git update-ref` and refused if the target branch was checked out
in any worktree. Operators had to switch or detach first. That is the wrong
daily loop.

`update-ref` on a checked-out branch moves the ref and leaves the index and
files on the old tree, so `git status` looks broken. A dirty worktree must
not be overwritten.

## Decision

1. **Ref update stays compare-and-swap.** `git update-ref refs/heads/<branch>
   <new> <expected-old>` is still the apply primitive. A moved tip is stale.

2. **Not checked out.** If no worktree has the target branch, only the ref is
   updated (previous behavior).

3. **Checked out and clean.** If a worktree has the branch, it must be clean
   (`git status --porcelain` empty, including untracked) and `HEAD` must equal
   the expected old tip. After a successful `update-ref`, that worktree is
   `git reset --hard <new>` so files match the applied commit.

4. **Checked out and dirty.** Apply refuses. It does not stash, merge, or
   leave a moved ref with leftover local edits.

Git does not allow the same branch in two worktrees, so at most one worktree
is refreshed.

## Consequences

- `init → propose → review → approve → apply` works on a normal `main`.
- Dirty trees stay operator-owned.
- Failure after `update-ref` and before `reset --hard` is rare (for example
  disk full). The ref is already the applied commit; `git reset --hard HEAD`
  recovers the files.

## Alternatives considered

- **Always refuse checked-out (status quo):** rejected. Forces Git plumbing.
- **update-ref and leave a dirty-looking worktree:** rejected. Confusing.
- **`git merge --ff-only` instead of update-ref:** rejected. Loses the
  expected-old compare-and-swap on the ref.
