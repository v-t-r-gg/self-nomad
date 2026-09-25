# Releasing self-nomad

Maintainer procedure for cutting a release candidate or final release from a
**clean, reviewed `main`**. Derive the version from packaging metadata — never
hard-code a release version into this document.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Permission to push tags
- Optional GPG key (`SELF_NOMAD_GPG_KEY`) for a local `SHA256SUMS.asc`
- Optional PyPI credentials only when intentionally publishing

```bash
git status
git pull --ff-only origin main
```

## 1. Resolve version

```bash
VERSION="$(uv run python scripts/release_meta.py version)"
echo "$VERSION"
uv run python scripts/release_meta.py tag
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

## 4. Clean rebuild, checksums, smoke, acceptance

```bash
uv run python scripts/build_release.py
ls -la dist/
uv run python scripts/checksums.py verify
uv run python scripts/release_smoke.py
uv run python scripts/mcp_smoke.py
uv run python scripts/operator_acceptance.py
```

Expect `self_nomad-${VERSION}-py3-none-any.whl`, `self_nomad-${VERSION}.tar.gz`,
and `SHA256SUMS`. Optional: `uv run python scripts/build_release.py --gpg`.

Confirm CLI version, metadata version, and (MCP) `server_info.version` agree
with `$VERSION` and are never `0+unknown`.

If a previous release wheel is on disk, pass `--previous-wheel` to the
operator-acceptance harness for a pip upgrade check.

## 5. Tag and GitHub pre-release

Only from the release commit on `main` after CI is green:

```bash
git tag -a "v${VERSION}" -m "self-nomad ${VERSION}"
git push origin "v${VERSION}"
```

Pushing `v*` runs `.github/workflows/release.yml`: clean rebuild, operator
acceptance, GitHub Artifact Attestations on the wheel/sdist/`SHA256SUMS`, and
a GitHub Release (`prerelease: true` when the version contains `rc` or `dev`).
Attach verification notes from `docs/releases/` when that file exists.

Do not create the GitHub Release by hand unless the workflow cannot run.

## 6. Optional package index

Publish only when intentionally shipping:

```bash
# example — use your org's preferred trusted publisher / twine flow
twine upload dist/*
```

Prefer TestPyPI before production PyPI for first-time pipelines.

## 7. Post-release development version

Bump `project.version` in `pyproject.toml` to the next `.dev0` (or patch),
refresh the lockfile if needed, and open a small PR. Do **not** reintroduce a
hard-coded version fallback in source; the uninstalled sentinel remains
`0+unknown`.

## Stop conditions

- Dirty worktree or unmerged docs/product PRs
- Failing smoke, operator acceptance, or coverage floor
- Version mismatch among pyproject, artifact names, CLI, and the git tag
- Incomplete changelog for the version being tagged
- Missing `SHA256SUMS` or failed checksum verify
