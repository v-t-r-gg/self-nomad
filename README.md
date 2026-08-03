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

**Release candidate `0.1.0rc1`.** The deterministic core supports repository
initialization and validation, isolated Git proposals with typed file
operations, review, validation, approval, stale detection, atomic target-ref
application, and committed audit records. Hermes and OpenClaw adapters provide
deterministic detection, import/restore plans, explicit fidelity and exclusion
reporting, verified backups, and atomic file writes.

Supported Python versions: **3.11, 3.12, and 3.13**. The package is intended to
be **OS-independent**; CI exercises Ubuntu (3.11–3.13) plus macOS and Windows
(3.13).

## Install

### From a built wheel (recommended for evaluation)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install dist/self_nomad-0.1.0rc1-py3-none-any.whl
self-nomad --version
```

Build the wheel yourself from a clean checkout:

```bash
uv sync --extra dev
uv build
uv run python scripts/release_smoke.py   # optional installed-artifact checks
```

### From source (development)

```bash
git clone https://github.com/v-t-r-gg/self-nomad.git
cd self-nomad
uv sync --extra dev
uv run self-nomad --version
```

Requires [uv](https://docs.astral.sh/uv/) and a local `git` on `PATH`.

## Quick start

```bash
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
# The target branch must not be checked out in any worktree.
git switch -c review-work
uv run self-nomad --repo /tmp/example apply PROPOSAL_ID
```

## Preview-first adapters

Runtime operations **preview by default**. `--yes` confirms the displayed class
of mutation; it never enables secret or session migration. Imports create
proposals and do not directly change the active branch.

```bash
self-nomad --repo ./my-agent detect --adapter hermes
self-nomad --repo ./my-agent import --adapter hermes --from ~/.hermes
self-nomad --repo ./my-agent import --adapter hermes --from ~/.hermes --yes
self-nomad --repo ./my-agent restore --adapter openclaw \
  --to ~/.openclaw/workspace
self-nomad --repo ./my-agent restore --adapter openclaw \
  --to ~/.openclaw/workspace --yes
```

## Checked-out-target rule

Proposal validation requires a clean isolated worktree and an exact match
between the complete committed Git tree and declared operations. Approval is
invalidated by staged, unstaged, untracked, or committed mutation. Application
**refuses to advance a branch checked out in any worktree**, avoiding stale
index and working-directory state. Detach or switch the target branch away
before `apply`.

## Security boundary

Restore is transactional: self-nomad builds and verifies a complete sibling
runtime tree, backs up affected artifacts, swaps the directory, verifies it
again, and restores the original automatically on failure.

The product boundary deliberately excludes credentials, sessions, databases,
and other runtime-owned state. Secret scanning catches high-confidence patterns
and is **not** general-purpose data-loss prevention. Configured Git
clean/smudge/process filters are **trusted local infrastructure**—do not use
self-nomad with an untrusted filter executable.

See [docs/threat-model.md](docs/threat-model.md) and
[SECURITY.md](SECURITY.md).

## Release limitations (plain language)

| Topic | Behavior |
| --- | --- |
| Target branch checkout | Must be detached or switched away before proposal application |
| Git filters | Clean/smudge/process filters are trusted local infrastructure |
| Credentials / sessions / DBs | Stay outside migration; never imported or restored as portable self |
| Secret scanning | High-confidence patterns only; not full DLP |

## Documentation

- [Repository format](docs/repository-format.md)
- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Adapter authoring](docs/adapter-authoring.md)
- [Releasing](docs/releasing.md) (maintainers)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
