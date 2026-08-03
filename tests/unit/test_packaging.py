"""Distribution content and packaging invariants for release artifacts.

These tests inspect built wheels/sdists when present under dist/, and always
validate source-tree packaging markers (py.typed, license, modules).
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_MODULES = (
    "self_nomad/__init__.py",
    "self_nomad/cli.py",
    "self_nomad/application.py",
    "self_nomad/py.typed",
    "self_nomad/adapters/hermes.py",
    "self_nomad/adapters/openclaw.py",
    "self_nomad/proposals/service.py",
    "self_nomad/repository/self_repository.py",
)


def test_source_tree_includes_typing_marker_and_license() -> None:
    assert (ROOT / "src/self_nomad/py.typed").is_file()
    assert (ROOT / "LICENSE").is_file()
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text


def test_package_modules_exist() -> None:
    for relative in PACKAGE_MODULES:
        assert (ROOT / "src" / relative).is_file(), relative


def _find_artifacts() -> tuple[Path | None, Path | None]:
    dist = ROOT / "dist"
    if not dist.is_dir():
        return None, None
    wheels = sorted(dist.glob("self_nomad-*.whl"))
    sdists = sorted(dist.glob("self_nomad-*.tar.gz"))
    wheel = wheels[-1] if wheels else None
    sdist = sdists[-1] if sdists else None
    return wheel, sdist


@pytest.mark.skipif(_find_artifacts()[0] is None, reason="no wheel in dist/; run uv build first")
def test_wheel_contains_required_files() -> None:
    wheel, _ = _find_artifacts()
    assert wheel is not None
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    for module in PACKAGE_MODULES:
        assert module in names, f"missing {module} in {wheel.name}"
    license_names = [n for n in names if n.endswith("LICENSE") or n.endswith("licenses/LICENSE")]
    assert license_names, f"LICENSE missing from {wheel.name}"
    assert any(n.endswith(".dist-info/METADATA") for n in names)


@pytest.mark.skipif(_find_artifacts()[1] is None, reason="no sdist in dist/; run uv build first")
def test_sdist_contains_required_files() -> None:
    _, sdist = _find_artifacts()
    assert sdist is not None
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    # sdist roots are versioned: self_nomad-0.1.0rc1/...
    def has_suffix(suffix: str) -> bool:
        return any(name.endswith(suffix) for name in names)

    assert has_suffix("LICENSE")
    assert has_suffix("README.md")
    assert has_suffix("src/self_nomad/py.typed")
    assert has_suffix("src/self_nomad/cli.py")
    assert has_suffix("pyproject.toml")
