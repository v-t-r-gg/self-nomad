# Contributing

Use Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/). A local `git`
binary must be available on `PATH`.

## Canonical local verification (matches CI)

Run this sequence from a clean worktree before opening or updating a PR:

```bash
uv lock --check
uv sync --extra dev --extra mcp
uv run ruff check .
uv run mypy
uv run python scripts/export_proposal_request_schema.py --check
uv run python scripts/check_docs.py
uv run pytest --cov=self_nomad --cov-report=term-missing
uv build
uv run python scripts/release_smoke.py
uv run python scripts/mcp_smoke.py
```

| Step | Purpose |
| --- | --- |
| `uv lock --check` | Fail if `uv.lock` is out of sync with `pyproject.toml` |
| `uv sync --extra dev --extra mcp` | Runtime + dev tools + optional MCP SDK |
| `ruff` / `mypy` | Lint and strict type checks |
| `export_proposal_request_schema.py --check` | Packaged schema matches models |
| `check_docs.py` | Links, CLI names, MCP tool names, schema parity, examples |
| `pytest --cov` | Full suite with coverage floor |
| `uv build` | Wheel + sdist under `dist/` |
| `release_smoke.py` | Base install without MCP extra |
| `mcp_smoke.py` | Install with `[mcp]`; stdio tool list + status + schema |

CI runs the test matrix on Ubuntu (Python 3.11–3.13) and compatibility jobs on
macOS and Windows (Python 3.13), plus a dedicated distribution job.

### Coverage notes

- Prefer in-process Typer (`CliRunner`) tests so `cli.py` contributes to coverage.
- Keep at least one installed-command subprocess path.
- Subprocess coverage uses `COVERAGE_PROCESS_START` pointing at `pyproject.toml` in CI.
- Do not lower the floor to hide regressions.

## Cross-platform notes

- Isolate application state with temporary directories (`HOME` / `USERPROFILE`,
  `XDG_STATE_HOME`, `LOCALAPPDATA` — see `tests/helpers.py`).
- Path assertions should use `Path` APIs; portable relative paths use `/`.
- Git-dependent tests must configure local `user.name` and `user.email`.
- Avoid POSIX-only paths in product code (`/tmp`, `/dev/null`).

## Tests

Every public behavior should include tests. **Security-sensitive behavior
requires a negative test.** Do not execute tests stored inside a managed self
repository from product code.

Layout:

- `tests/unit/` — helpers, manifests, packaging, MCP surface
- `tests/integration/` — adapters, proposals, MCP in-process/stdio
- `tests/e2e/` — CLI
- `scripts/release_smoke.py` / `scripts/mcp_smoke.py` — installed artifacts

Do not import the MCP SDK from core packages outside `self_nomad.mcp_server`.

## Documentation

- Start from [docs/index.md](docs/index.md).
- Keep CLI option spelling aligned with live Typer help.
- Run `scripts/check_docs.py` before docs PRs.
- Do not hard-code release versions outside historical changelog/upgrading notes.

## Versioning

`project.version` in `pyproject.toml` is the packaging source of truth.
`self_nomad.__version__` reads installed metadata; uninstalled trees use the
sentinel `0+unknown`. Never hard-code a release version in library source.

## Pull requests

- Keep runtime dependencies minimal.
- Do not commit build products.
- Do not add telemetry, credential handling, GitPython, or LLM dependencies.
- Preserve repository schema version 1, stable JSON envelopes, and finding codes
  unless a narrow cross-platform fix requires a change.
- Leave tagging and PyPI publication to [docs/releasing.md](docs/releasing.md).
