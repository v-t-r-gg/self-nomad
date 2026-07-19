# self-nomad

an agent's self, untethered from its runtime.

`self-nomad` is a local-first Python CLI for putting an AI agent's durable
identity, curated memory, and skills under safe Git version control. Import an
existing agent, review changes as typed proposals, and restore the portable
self on another machine or supported runtime without copying credentials or
session databases.

It is not an agent runtime and it does not call an LLM. It is the portability
and change-governance layer around the agents you already run.

## Development status

The deterministic core is under development. The current slice supports
repository initialization and validation plus isolated Git proposals with
typed file operations, review, validation, approval, stale detection, atomic
target-ref application, and committed audit records. Hermes and OpenClaw
adapters provide deterministic detection, import/restore plans, explicit
fidelity and exclusion reporting, verified backups, and atomic file writes.

```bash
uv sync
uv run self-nomad init /tmp/example --name example
uv run self-nomad --repo /tmp/example validate --strict
```

A change document contains typed operations:

```yaml
operations:
  - kind: replace
    path: memory/MEMORY.md
    content_source: /tmp/candidate-memory.md
```

```bash
uv run self-nomad --repo /tmp/example propose \
  --reason "Add a curated fact" --change changes.yaml
uv run self-nomad --repo /tmp/example validate PROPOSAL_ID
uv run self-nomad --repo /tmp/example approve PROPOSAL_ID
uv run self-nomad --repo /tmp/example apply PROPOSAL_ID
```

Runtime operations preview by default:

```bash
self-nomad --repo ./my-agent detect --adapter hermes
self-nomad --repo ./my-agent import --adapter hermes --from ~/.hermes
self-nomad --repo ./my-agent import --adapter hermes --from ~/.hermes --yes
self-nomad --repo ./my-agent restore --adapter openclaw \
  --to ~/.openclaw/workspace
self-nomad --repo ./my-agent restore --adapter openclaw \
  --to ~/.openclaw/workspace --yes
```

`--yes` confirms the displayed class of mutation; it never enables secret or
session migration. Imports create proposals and do not directly change the
active branch.

See [docs/repository-format.md](docs/repository-format.md) for the format and
[docs/threat-model.md](docs/threat-model.md) for the security boundary.
