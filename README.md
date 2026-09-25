# self-nomad

an agent's self, untethered from its runtime.

`self-nomad` is a local-first Python toolkit for putting an AI agent's durable
identity, curated memory, and skills under safe Git version control. Import an
existing agent, review changes as typed proposals, and restore the portable
self on another machine or supported runtime **without** copying credentials
or session databases.

It is **not** an agent runtime, does not call an LLM, and is not a public
registry or marketplace. It is the portability and change-governance layer
around the agents you already run. A separate registry, if built, may consume
this toolkit for snapshot import and export; see
[docs/ecosystem.md](docs/ecosystem.md).

## Why it exists

Agent “selves” (persona, memory, skills) tend to live inside runtime-specific
directories mixed with secrets and sessions. self-nomad extracts a portable
Git repository, requires explicit review for mutations, and keeps approval and
branch advancement under operator control.

## Development status

**Version `1.3.0`**. Schema 1 and the 1.0 contracts stay frozen. Tag `v1.2.0` remains the TUI-only release. The deterministic core supports:

- Repository init and structural validation
- Isolated Git proposals (materialize → validate → approve → apply)
- Agent intake (`ProposalRequest` v1) with idempotent receipts
- Optional local stdio **MCP** surface for inspection and intake (no approve/apply)
- Hermes, OpenClaw, `agents-md`, and `claude-code` adapters (detect / import / restore), plus an
  unregistered authoring-kit sample (`example-files`)

Supported Python: **3.11, 3.12, 3.13**. CI exercises Ubuntu (3.11–3.13) plus
macOS and Windows (3.13).

## Interfaces at a glance

| Capability | CLI | Python | MCP |
| --- | --: | --: | --: |
| Wordmark / about | yes | no | no |
| Initialize repository | yes | yes | no |
| Validate repository | yes | yes | yes |
| Detect runtime | yes | yes | no |
| Import runtime | yes | yes | no |
| Restore runtime | yes | yes | no |
| Preview intake | yes | yes | yes |
| Submit proposal (intake) | yes | yes | yes |
| Validate proposal | yes | yes | yes |
| Pack / check / install snapshot | yes | yes | no |
| List proposals / applied log | yes | yes | no |
| Approve and apply | yes | yes | no |
| Interactive TUI | `self-nomad[tui]` | yes | no |

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install dist/self_nomad-*-py3-none-any.whl   # or: pip install 'self-nomad[mcp]'
self-nomad --version
```

Development checkout:

```bash
git clone https://github.com/v-t-r-gg/self-nomad.git
cd self-nomad
uv sync --extra dev
uv run self-nomad --version
```

Requires [uv](https://docs.astral.sh/uv/) (for development) and a local `git`
on `PATH`. Optional MCP: `uv sync --extra dev --extra mcp` or
`pip install 'self-nomad[mcp]'`.

## Five-minute quick start

```bash
# Linux/macOS example path; Windows: use an absolute path of your choice
uv run self-nomad init /tmp/example --name example
uv run self-nomad --repo /tmp/example validate --strict

# Typed change document
cat > /tmp/change.yaml <<'EOF'
operations:
  - kind: replace
    path: memory/MEMORY.md
    content_source: /tmp/candidate-memory.md
EOF
printf '# Memory\n\n- Hello from a proposal.\n' > /tmp/candidate-memory.md

uv run self-nomad --repo /tmp/example propose \
  --reason "Record a fact" --change /tmp/change.yaml
# note PROPOSAL_ID from the command output
uv run self-nomad --repo /tmp/example validate PROPOSAL_ID
uv run self-nomad --repo /tmp/example approve PROPOSAL_ID --identifier operator

uv run self-nomad --repo /tmp/example apply PROPOSAL_ID
```

Full walkthrough: [docs/getting-started.md](docs/getting-started.md).

## Safety boundary

- **No credentials, sessions, or runtime databases** in the portable self
- Proposals bind complete Git trees and declared diffs
- Approval is an explicit operator step (CLI/Python only; not exposed on MCP)
- Apply refreshes a clean checked-out target; dirty worktrees are refused
- Restore is transactional (stage → verify → backup → swap → verify → rollback)
- Secret scanning catches high-confidence patterns only — not general DLP
- Git clean/smudge/process filters are **trusted local infrastructure**

See [docs/threat-model.md](docs/threat-model.md) and [SECURITY.md](SECURITY.md).

## Documentation

Start at the **[documentation index](docs/index.md)**.

| For | Read |
| --- | --- |
| First repository | [Getting started](docs/getting-started.md) |
| Commands | [CLI reference](docs/cli-reference.md) |
| Python | [Python API](docs/python-api.md) |
| Hermes / OpenClaw | [Runtime portability](docs/runtime-portability.md) |
| Agents / MCP | [Agent intake](docs/agent-intake.md), [MCP](docs/mcp.md) |
| Contributors | [Architecture](docs/architecture.md), [Contributing](CONTRIBUTING.md) |

## Development

```bash
uv lock --check
uv sync --extra dev --extra mcp
uv run ruff check .
uv run mypy
uv run python scripts/export_proposal_request_schema.py --check
uv run python scripts/check_docs.py
uv run pytest --cov=self_nomad --cov-report=term-missing
uv build
uv run python scripts/build_release.py
uv run python scripts/release_smoke.py
uv run python scripts/mcp_smoke.py
uv run python scripts/operator_acceptance.py
```

## License

MIT. See [LICENSE](LICENSE).
