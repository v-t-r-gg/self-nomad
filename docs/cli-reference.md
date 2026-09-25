# CLI reference

Derived from the Typer registry (`self-nomad --help` and subcommand help).
Global options apply to all commands:

| Option | Purpose |
| --- | --- |
| `--repo <path>` | Self repository root (required for most ops; `init` takes a path argument) |
| `--json` | Stable machine-readable envelope (`schema_version`, `command`, `ok`, `result`, `warnings`, `errors`) |
| `--version` | Print package version |
| `--help` | Command help |

Entry points: `self-nomad` (core), `self-nomad-mcp` (optional MCP extra).

Human output uses Rich panels and, on a color TTY (or `SELF_NOMAD_BANNER=1`),
the self-nomad wordmark on help, `about`, and `init`. `--json` is unchanged.
`NO_COLOR` and `SELF_NOMAD_BANNER=0` suppress the mark.

---

## Repository management

### `self-nomad about`

| | |
| --- | --- |
| Purpose | Print the wordmark, version, and what this tool is not |
| Mutation | None |
| JSON | Yes (`name`, `version`, `tagline`) |

```bash
self-nomad about
```

---

### `self-nomad pack`

| | |
| --- | --- |
| Purpose | Write a history-free snapshot, or verify one with `--check` |
| Mutation | Writes `--out` (pack). `--check` is read-only |
| Arguments | `--out`, `--profile specialist\|personal` (default specialist), `--include-long-term-memory`, `--check PATH`, `--list PATH` |
| JSON | Yes. `--check` result includes `profile`, `omitted`, `content_digest`, `skills`, `packer_version` |

Specialist packs omit `user_profile` and daily memory. Long-term memory is
omitted unless `--include-long-term-memory`, and then only `memory/PUBLISH.md`
is packed — not `memory/MEMORY.md`. `pack --check` accepts a personal archive
only with `--profile personal`. The archive is gzip tar, not a Git clone.
Sidecar `self-nomad.pack.json` is additive and does not change repository
schema 1. See [snapshot.md](snapshot.md).

```bash
self-nomad --repo ./agent pack --out ./agent.snpack
self-nomad pack --check ./agent.snpack
```

### `self-nomad install`

| | |
| --- | --- |
| Purpose | Extract a pack into a **new** local repository after validation |
| Mutation | Creates destination tree; optional Git commit |
| Arguments | `ARCHIVE`, `--to` (required), `--git` / `--no-git` |
| JSON | Yes (`repository`, `content_digest`, `summary`) |

Destination must be missing or empty. The pack is extracted to a staging
directory and validated (`--strict`, digest check, no `.git`, no links)
**before** anything is written to `--to`.

```bash
self-nomad install ./agent.snpack --to ./local-copy
```

---

### `self-nomad init`

| | |
| --- | --- |
| Purpose | Create a conservative self repository |
| Mutation | Creates files; optional initial Git commit |
| Preview | No |
| Arguments | `path` (required), `--name` (required), `--description`, `--git` / `--no-git` |
| JSON | Yes |

```bash
self-nomad init /tmp/agent --name demo --description "Portable self"
```

### `self-nomad validate`

| | |
| --- | --- |
| Purpose | Validate repository structure **or** a proposal when `proposal_id` is given |
| Mutation | Repository-only: none. With proposal id: may advance `materialized → validated` |
| Preview | Repository validation is read-only |
| Arguments | optional `proposal_id`, `--strict` |
| JSON | Yes |

```bash
self-nomad --repo ./agent validate --strict
self-nomad --repo ./agent validate PROPOSAL_ID
```

### `self-nomad status`

| | |
| --- | --- |
| Purpose | Repository identity and validation summary |
| Mutation | None |
| JSON | Yes |

---

## Proposal management

### `self-nomad proposals`

| | |
| --- | --- |
| Purpose | List local proposal records, newest first |
| Mutation | None |
| JSON | Yes (`proposals`: id, status, reason, risk, target_branch) |

### `self-nomad log`

| | |
| --- | --- |
| Purpose | Applied proposal commits from Git (`self-nomad(audit):` subjects) |
| Mutation | None |
| Arguments | `--limit` (default 20) |
| JSON | Yes (`commits`: commit, subject) |

History comes from the repository Git log, not platform proposal state.

### `self-nomad propose`

| | |
| --- | --- |
| Purpose | Materialize a typed change document in an isolated worktree |
| Mutation | Creates proposal state (materialized) |
| Arguments | `--reason` (required), `--change` file (required), `--target-branch` |
| JSON | Yes |

Change documents list `add` / `replace` / `delete` operations with
`content_source` paths for file bytes.

### `self-nomad review`

| | |
| --- | --- |
| Purpose | Show proposal provenance, operations, unified diff, and state |
| Mutation | None unless `--interactive` (approve or reject only; never apply) |
| Arguments | `proposal_id`, `--interactive`, `--identifier` |
| JSON | Yes (record plus `unified_diff` when the proposal is materialized) |

`--interactive` cannot be combined with `--json`. Approve records an
identifier and does not apply. Materialized proposals are validated before
approval. Applied / rejected / stale / failed proposals are display-only.

### `self-nomad approve`

| | |
| --- | --- |
| Purpose | Record approval for a **validated** proposal |
| Mutation | `validated → approved` |
| Arguments | `proposal_id`, `--identifier` |
| JSON | Yes |

Does not authenticate the identifier.

### `self-nomad apply`

| | |
| --- | --- |
| Purpose | Atomically advance the target ref to an approved proposal |
| Mutation | `approved → applied` (or stale on conflict) |
| Arguments | `proposal_id` |

Compare-and-swap on the target ref. A **clean** checked-out worktree is
refreshed to the applied commit. A **dirty** worktree is refused
([ADR 0008](decisions/0008-apply-checked-out-worktree.md)).

### `self-nomad reject`

| | |
| --- | --- |
| Purpose | Reject a pending proposal |
| Mutation | Marks rejected |
| Arguments | `proposal_id`, `--reason` (required) |

---

## Runtime adapters

### `self-nomad detect`

| | |
| --- | --- |
| Purpose | Detect compatible runtime instances without mutation |
| Mutation | None |
| Arguments | `--adapter` (default `hermes`), `--path` |

### `self-nomad diff`

| | |
| --- | --- |
| Purpose | Deterministic import or restore drift without writes |
| Mutation | None |
| Arguments | `--adapter` (required), `--direction` (required: import\|restore), `--path` |

### `self-nomad import`

| | |
| --- | --- |
| Purpose | Plan an import; with `--yes`, create an isolated proposal |
| Mutation | Preview default; `--yes` materializes a proposal (does not apply) |
| Arguments | `--adapter` (required), `--from`, `--reason`, `--yes` |

### `self-nomad restore`

| | |
| --- | --- |
| Purpose | Plan a restore; apply only with `--yes` |
| Mutation | Preview default; `--yes` performs transactional restore |
| Arguments | `--adapter` (required), `--to` (required), `--yes` |

---

## Agent intake

### `self-nomad intake`

| | |
| --- | --- |
| Purpose | Preview (default) or submit a `ProposalRequest` JSON file |
| Mutation | Preview: zero-write. `--submit`: creates/materializes proposal |
| Arguments | `--request` (required), `--submit` |
| JSON | Recommended (`--json`) |

```bash
self-nomad --repo ./agent --json intake --request request.json
self-nomad --repo ./agent --json intake --request request.json --submit
```

---

## Machine-readable output

With `--json`, successful and failed commands share:

```json
{
  "schema_version": 1,
  "command": "validate",
  "ok": true,
  "result": {},
  "warnings": [],
  "errors": []
}
```

Error objects use stable codes. See [agent-intake.md](agent-intake.md) and
application exception types in `self_nomad.errors`.

## MCP entry point

```bash
self-nomad-mcp --repo /absolute/path/to/agent-self
```

Requires `pip install 'self-nomad[mcp]'`. Not a subcommand of `self-nomad`.
See [mcp.md](mcp.md).
