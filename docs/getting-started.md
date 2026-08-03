# Getting started

One coherent operator journey from an empty directory to an applied proposal.
Commands use temporary paths; substitute absolute paths on your machine.
Windows PowerShell users should swap path separators and use
`.venv\Scripts\activate` when working from source.

## Prerequisites

- Python 3.11+
- `git` on `PATH`
- Either a built wheel or a development checkout with [uv](https://docs.astral.sh/uv/)

```bash
# from a development checkout
uv sync --extra dev
uv run self-nomad --version
```

## 1. Initialize a self repository

```bash
uv run self-nomad init /tmp/agent-self --name demo-agent
```

Creates a Git repository (unless `--no-git`), writes `self-nomad.yaml`,
`policy/policy.yaml`, and seed identity/memory files, then commits the initial
tree when Git is enabled.

## 2. Inspect the generated tree

Typical layout (schema version 1):

```text
self-nomad.yaml
policy/policy.yaml
identity/instructions.md
identity/persona.md
identity/identity.md
identity/user.md
memory/MEMORY.md
tools/notes.md
skills/          # may be empty initially
```

Machine-local paths never belong in the portable tree; use
`.self-nomad.local.yaml` (ignored) if needed.

## 3. Strict validation

```bash
uv run self-nomad --repo /tmp/agent-self validate --strict
# machine-readable:
uv run self-nomad --repo /tmp/agent-self --json validate --strict
```

Repository tests under the self tree are **not** executed (`execute_repository_tests` is false by policy).

## 4. Prepare a typed change document

```bash
printf '# Memory\n\n- Prefers concise documentation.\n' > /tmp/candidate-memory.md

cat > /tmp/change.yaml <<'EOF'
operations:
  - kind: replace
    path: memory/MEMORY.md
    content_source: /tmp/candidate-memory.md
EOF
```

Operations are `add`, `replace`, or `delete`. Paths are repository-relative
POSIX paths.

## 5. Materialize a proposal

```bash
uv run self-nomad --repo /tmp/agent-self propose \
  --reason "Record a documentation preference" \
  --change /tmp/change.yaml
```

Copy the `proposal_id` (UUID) from the output. State:

```text
draft → materialized
```

The active branch is not rewritten; work happens on an isolated proposal
branch and worktree under private platform state.

## 6. Review and validate

```bash
uv run self-nomad --repo /tmp/agent-self review PROPOSAL_ID
uv run self-nomad --repo /tmp/agent-self validate PROPOSAL_ID
```

Validation re-checks the complete tree, declared diff, and secret patterns:

```text
materialized → validated
```

## 7. Approve

```bash
uv run self-nomad --repo /tmp/agent-self approve PROPOSAL_ID --identifier operator
```

```text
validated → approved
```

self-nomad records `approval_identifier`; it does **not** authenticate the
caller. Any later tree drift marks the proposal **stale**.

## 8. Detach the target branch

**Apply refuses a target branch checked out in any worktree.** Switch away
first:

```bash
git -C /tmp/agent-self switch -c review-work
# or: git -C /tmp/agent-self switch --detach
```

## 9. Apply

```bash
uv run self-nomad --repo /tmp/agent-self apply PROPOSAL_ID
```

```text
approved → applied
```

Uses `git update-ref` with the expected old tip. A moved target becomes stale;
there is no implicit merge.

## 10. Inspect audit and history

```bash
git -C /tmp/agent-self log --oneline -5
uv run self-nomad --repo /tmp/agent-self status
```

Applied proposals leave committed audit metadata on the proposal branch and
advance the target ref atomically.

## Expected state transitions

Happy path:

```text
draft → materialized → validated → approved → applied
```

Other terminal outcomes:

| Status | Meaning |
| --- | --- |
| `rejected` | Operator rejected before apply |
| `stale` | Target tip or content digest no longer matches |
| `failed` | Materialization/apply failure recorded for recovery |

## Agent intake alternative

Instead of a YAML change file, agents may submit JSON:

```bash
uv run self-nomad --repo /tmp/agent-self --json intake --request request.json
uv run self-nomad --repo /tmp/agent-self --json intake --request request.json --submit
```

See [agent-intake.md](agent-intake.md) and [examples/e2e/](../examples/e2e/).

## Next

- [CLI reference](cli-reference.md)
- [Runtime import/restore](runtime-portability.md)
- [MCP for agents](mcp.md)
