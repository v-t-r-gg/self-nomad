#!/usr/bin/env python3
"""Clean rebuild of wheel, sdist, and SHA256SUMS for a release candidate.

Removes previous dist/build outputs, invokes the project build backend, then
writes and verifies ``dist/SHA256SUMS``. Optional GPG detach-sign of the
checksum file when ``--gpg`` is passed or a signing key is configured.

Usage (from repository root)::

    uv run python scripts/build_release.py
    uv run python scripts/build_release.py --gpg
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.checksums import gpg_sign, verify_checksums, write_checksums  # noqa: E402
from scripts.release_meta import project_version  # noqa: E402


class BuildError(RuntimeError):
    """Raised when the clean rebuild fails."""


def _run(command: list[str], *, step: str) -> None:
    completed = subprocess.run(command, check=False, capture_output=True, text=True, cwd=ROOT)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise BuildError(f"{step} failed: {' '.join(command)}\n{detail}")


def clean_build_trees(root: Path = ROOT) -> None:
    for relative in ("dist", "build"):
        path = root / relative
        if path.exists():
            shutil.rmtree(path)
    for leftover in root.glob("*.egg-info"):
        shutil.rmtree(leftover)
    src_egg = root / "src"
    if src_egg.is_dir():
        for leftover in src_egg.glob("*.egg-info"):
            shutil.rmtree(leftover)


def build_artifacts(root: Path = ROOT) -> None:
    uv = shutil.which("uv")
    if uv is not None:
        _run([uv, "build"], step="uv build")
        return
    _run([sys.executable, "-m", "build"], step="python -m build")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--gpg", action="store_true")
    parser.add_argument("--gpg-key", default="")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    dist_dir = root / "dist"
    try:
        version = project_version(root)
        clean_build_trees(root)
        build_artifacts(root)
        if not dist_dir.is_dir():
            raise BuildError(f"build produced no dist directory: {dist_dir}")
        write_checksums(dist_dir)
        verify_checksums(dist_dir)
        signature = gpg_sign(
            dist_dir / "SHA256SUMS",
            key=args.gpg_key or None,
            required=args.gpg,
        )
    except (BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Rebuilt artifacts for {version}:")
    for path in sorted(dist_dir.iterdir()):
        if path.is_file():
            print(f"  {path.name}  {path.stat().st_size} bytes")
    if signature is None:
        print("GPG signature not produced (attestations cover tagged GitHub releases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
