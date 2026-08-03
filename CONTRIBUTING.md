# Contributing

Use Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/). A local `git`
binary must be available on `PATH`.

## Canonical local verification (matches CI)

Run this sequence from a clean worktree before opening or updating a PR:

```bash
uv lock --check
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest --cov=self_nomad --cov-report=term-missing
uv build
uv run python scripts/release_smoke.py
```

| Step | Purpose |
| --- | --- |
| `uv lock --check` | Fail if `uv.lock` is out of sync with `pyproject.toml` |
| `uv sync --extra dev` | Install runtime + dev tools into the project environment |
| `ruff` / `mypy` | Lint and strict type checks |
| `pytest --cov` | Full suite with coverage floor (`fail_under` in `pyproject.toml`) |
| `uv build` | Produce wheel + sdist under `dist/` |
| `scripts/release_smoke.py` | Fresh venv install of each artifact; CLI init + strict JSON validate |

CI also runs the test matrix on Ubuntu (Python 3.11–3.13) and compatibility jobs
on macOS and Windows (Python 3.13), plus a dedicated distribution job.

### Coverage notes

- Prefer in-process Typer (`CliRunner`) tests so `cli.py` contributes to the
  combined report.
- Keep at least one installed-command subprocess path (see
  `tests/e2e/test_cli_subprocess.py`).
- Subprocess coverage is enabled when `COVERAGE_PROCESS_START` points at
  `pyproject.toml` (set automatically in CI).
- The floor is intentionally slightly below the measured plateau so platform
  variance does not flake; do not lower it to hide regressions.

## Cross-platform notes

- Isolate application state with temporary directories. Tests should set
  `HOME` / `USERPROFILE`, `XDG_STATE_HOME`, and `LOCALAPPDATA` (see
  `tests/helpers.py`) rather than writing into the real user profile.
- Path assertions should use `Path` APIs; prefer `.as_posix()` only when a
  portable relative path string is required (manifest paths use `/`).
- Git-dependent tests must configure local `user.name` and `user.email` inside
  the temporary repository.
- Do not assume POSIX-only paths (`/tmp`, `/dev/null`) in new product code;
  use `tempfile` and platform-neutral helpers.
- Windows runners need Git for Windows on `PATH` (provided on GitHub-hosted
  `windows-latest`).

## Tests

Every public behavior should include tests. **Security-sensitive behavior
requires a negative test** proving the unsafe case is rejected (path escape,
symlink abuse, secret patterns, oversize content, checked-out target apply,
and similar).

Do not execute tests or scripts stored inside a managed self repository from
product code. Fixture data under `tests/fixtures/` is fine for the suite
itself.

Layout:

- `tests/unit/` — pure helpers, manifests, packaging, version
- `tests/integration/` — adapters and proposal service
- `tests/e2e/` — CLI (in-process Typer + one subprocess path)
- `scripts/release_smoke.py` — installed wheel/sdist only (not the editable tree)

## Versioning

`project.version` in `pyproject.toml` is the packaging source of truth.
`self_nomad.__version__` reads installed metadata via `importlib.metadata`.
An uninstalled source tree falls back to the sentinel `0+unknown`—never a
hard-coded release version. Tests and the release smoke harness must derive
expected versions from `pyproject.toml` or installed/artifact metadata, not
string literals for a specific release.

## Pull requests

- Keep runtime dependencies minimal.
- Do not commit build products (`dist/`, wheels, coverage data).
- Do not add telemetry, credential handling, GitPython, or LLM dependencies.
- Preserve repository schema version 1, stable JSON envelope fields, and
  existing finding/error codes unless a cross-platform defect requires a
  narrow fix.
- Leave tagging, GitHub Releases, and PyPI publication to the process in
  [docs/releasing.md](docs/releasing.md).
