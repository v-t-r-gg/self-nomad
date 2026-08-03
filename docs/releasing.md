# Releasing self-nomad

Maintainer procedure for cutting a release candidate or final release from a
**clean, reviewed `main`**. Derive the version from packaging metadata — never
hard-code a release version into this document.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Permission to push tags
- Optional PyPI credentials only when intentionally publishing

```bash
git status
git pull --ff-only origin main
```

## 1. Resolve version

```bash
VERSION="$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
echo "$VERSION"
```

Uninstalled source trees report `0+unknown` via `self_nomad.__version__`;
**installed** artifacts and `self-nomad --version` must match `$VERSION`.

## 2. Lock and sync

```bash
uv lock --check
uv sync --extra dev --extra mcp
```

## 3. Quality gates

```bash
uv run ruff check .
uv run mypy
uv run python scripts/export_proposal_request_schema.py --check
uv run python scripts/check_docs.py
uv run pytest --cov=self_nomad --cov-report=term-missing
```

Coverage must meet `tool.coverage.report.fail_under` in `pyproject.toml`.

## 4. Clean build

```bash
rm -rf dist build *.egg-info src/*.egg-info
uv build
ls -la dist/
```

Expect `self_nomad-${VERSION}-py3-none-any.whl` and `self_nomad-${VERSION}.tar.gz`.

## 5. Artifact smoke

```bash
uv run python scripts/release_smoke.py   # base install, no MCP extra
uv run python scripts/mcp_smoke.py       # install with [mcp]
```

Confirm CLI version, metadata version, and (MCP) `server_info.version` agree
with `$VERSION` and are never `0+unknown`.

## 6. Checksums

```bash
uv run python - <<'PY'
import hashlib
from pathlib import Path
for path in sorted(Path("dist").iterdir()):
    if path.is_file():
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
PY
```

## 7. Tag and GitHub Release

Only from the release commit on `main` after CI is green:

```bash
git tag -a "v${VERSION}" -m "self-nomad ${VERSION}"
git push origin "v${VERSION}"
```

Create a GitHub Release (pre-release for `rc` versions). Attach wheel, sdist,
and checksums.

## 8. Optional package index

Publish only when intentionally shipping:

```bash
# example — use your org's preferred trusted publisher / twine flow
twine upload dist/*
```

Prefer TestPyPI before production PyPI for first-time pipelines.

## 9. Post-release development version

Bump `project.version` in `pyproject.toml` to the next `.dev0` (or patch),
refresh the lockfile if needed, and open a small PR. Do **not** reintroduce a
hard-coded version fallback in source; the uninstalled sentinel remains
`0+unknown`.

## Stop conditions

- Dirty worktree or unmerged docs/product PRs
- Failing smoke or coverage floor
- Version mismatch among pyproject, artifact names, and CLI
- Incomplete changelog for the version being tagged
