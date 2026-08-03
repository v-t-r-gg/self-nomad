# Releasing self-nomad

Maintainer procedure for cutting a release candidate or final release from a
clean, reviewed tree. This document is the source of truth for lock
verification, quality gates, artifact smoke tests, checksums, tagging, GitHub
Release creation, and optional PyPI publication.

Do **not** tag or publish from an unfinished feature branch. The v0.1 release
candidate PR prepares packaging; promotion to a tag requires explicit
maintainer approval after CI is green.

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- Git with permission to push tags to `origin`
- (Optional) PyPI / TestPyPI credentials only when intentionally publishing
- Working directory is a clean checkout of the release commit on `main` (or the
  agreed release branch)

## 1. Synchronize and verify the lockfile

```bash
git status
git pull --ff-only origin main
uv lock --check
uv sync --extra dev
```

`uv lock --check` must exit 0. If it fails, regenerate with `uv lock`, review
the diff, and commit it in a dedicated change—not as part of an unrelated PR.

## 2. Quality checks (match CI)

```bash
uv run ruff check .
uv run mypy
uv run pytest --cov=self_nomad --cov-report=term-missing
```

All must pass. Coverage must meet the configured floor in `pyproject.toml`
(`tool.coverage.report.fail_under`). CLI paths are included via in-process
Typer tests; subprocess CLI coverage is enabled when
`COVERAGE_PROCESS_START` points at `pyproject.toml` (CI sets this).

## 3. Clean builds

Remove prior artifacts so checksums and smoke tests cannot use stale files:

```bash
rm -rf dist build *.egg-info src/*.egg-info
uv build
ls -la dist/
```

Expect exactly one wheel and one sdist, for example:

- `dist/self_nomad-0.1.0rc1-py3-none-any.whl`
- `dist/self_nomad-0.1.0rc1.tar.gz`

Version in the artifact names must match `project.version` in `pyproject.toml`
and `self_nomad.__version__`.

## 4. Artifact inspection

```bash
uv run python - <<'PY'
import tarfile, zipfile
from pathlib import Path
for path in sorted(Path("dist").iterdir()):
    print("==", path.name)
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        assert "self_nomad/py.typed" in names
        assert any(n.endswith("LICENSE") for n in names)
        assert "self_nomad/cli.py" in names
        print("wheel OK:", len(names), "entries")
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as t:
            names = t.getnames()
        assert any(n.endswith("LICENSE") for n in names)
        assert any(n.endswith("README.md") for n in names)
        assert any(n.endswith("src/self_nomad/py.typed") for n in names)
        print("sdist OK:", len(names), "entries")
PY
```

## 5. Installed-artifact smoke tests

Operate against `dist/` only—never editable mode:

```bash
uv run python scripts/release_smoke.py
```

For each wheel and sdist the harness:

1. Creates a fresh temporary virtual environment
2. Installs the artifact (non-editable)
3. Asserts `import self_nomad` and version `0.1.0rc1` (or the release version)
4. Runs `self-nomad --version` and `self-nomad --help`
5. Initializes a temporary repository and runs strict JSON validation
6. Confirms `py.typed` is present on the installed package

Failures name the artifact and command. Re-run only after fixing and
rebuilding; do not tag on smoke failure.

## 6. Checksums

```bash
# Platform-neutral SHA-256 (Python)
uv run python - <<'PY'
import hashlib
from pathlib import Path
for path in sorted(Path("dist").iterdir()):
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.name}")
PY
```

Record checksums in the GitHub Release notes.

## 7. Tag creation

Only after steps 1–6 succeed on the exact commit to release:

```bash
# Example for the release candidate
git tag -a v0.1.0rc1 -m "self-nomad 0.1.0rc1"
git push origin v0.1.0rc1
```

Tag name is `v` + the PEP 440 version (`v0.1.0rc1`, later `v0.1.0`).

Do not move or force-push release tags.

## 8. GitHub Release

Create a GitHub Release for the tag:

1. Title: `0.1.0rc1` (or final version)
2. Body: paste the matching `CHANGELOG.md` section
3. Attach `dist/*` wheel and sdist
4. Include SHA-256 checksums
5. Mark pre-releases (`rc`, `a`, `b`) as **pre-release** in the GitHub UI

```bash
gh release create v0.1.0rc1 \
  dist/self_nomad-0.1.0rc1-py3-none-any.whl \
  dist/self_nomad-0.1.0rc1.tar.gz \
  --title "0.1.0rc1" \
  --notes-file <(sed -n '/## \[0.1.0rc1\]/,/## \[/p' CHANGELOG.md | head -n -1) \
  --prerelease
```

Adjust notes extraction as needed; prefer pasting the curated changelog section.

## 9. Optional PyPI publication

Publication is **not** part of the default RC checklist. When explicitly
approved:

```bash
# TestPyPI first (recommended)
uv run twine check dist/*
uv run twine upload --repository testpypi dist/*

# Production PyPI only after TestPyPI install verification
uv run twine upload dist/*
```

Verify with a clean environment:

```bash
uv venv /tmp/self-nomad-pypi && \
  uv pip install --python /tmp/self-nomad-pypi self-nomad==0.1.0rc1 && \
  /tmp/self-nomad-pypi/bin/self-nomad --version
```

## 10. Post-release

1. Bump `project.version` in `pyproject.toml` to the next development version
   (for example `0.1.0.dev1` or `0.1.1.dev0`).
2. Align the narrow source-tree fallback in `src/self_nomad/__init__.py` if it
   still hard-codes a version string.
3. Add a new empty `## [Unreleased]` section at the top of `CHANGELOG.md` if
   the release consumed the previous Unreleased notes.
4. Open a follow-up PR for the version bump; do not amend the release tag.

## Version agreement rules

| Surface | Source |
| --- | --- |
| Wheel / sdist filename | `project.version` in `pyproject.toml` |
| `importlib.metadata.version("self-nomad")` | installed package metadata |
| `self_nomad.__version__` | `importlib.metadata` (fallback only when uninstalled) |
| `self-nomad --version` | `self_nomad.__version__` |

All four must agree for a release commit.

## Security notes for releasers

- Never attach private agent repositories, credentials, or session data to a
  release.
- Confirm `CHANGELOG.md` and release notes do not include secret material.
- Releasing does not change the security boundary documented in
  `docs/threat-model.md` and `SECURITY.md`.
