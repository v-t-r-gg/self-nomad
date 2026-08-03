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

---

## Repository management

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
| Purpose | Show proposal provenance, operations, and state |
| Mutation | None |
| Arguments | `proposal_id` |

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

**Requires the target branch not checked out in any worktree.**

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
