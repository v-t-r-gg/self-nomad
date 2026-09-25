"""Hub transport always checks before install and never uploads."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from self_nomad.application import SelfNomad
from self_nomad.errors import ConflictError, PackError
from self_nomad.hub.client import publish_pack, pull_pack
from self_nomad.snapshot import PACK_SIDECAR


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "agent"
    SelfNomad.initialize(root, name="hub-agent", initialize_git=False)
    return root


def test_pull_checks_then_installs_and_omits_user(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    archive = tmp_path / "agent.snpack"
    SelfNomad.open(root).pack(archive, profile="specialist")
    destination = tmp_path / "installed"
    summary = pull_pack(str(archive), destination)
    assert summary.profile == "specialist"
    assert not (destination / "identity" / "user.md").exists()
    assert (destination / "self-nomad.yaml").is_file()


def test_pull_rejects_forged_sidecar_without_writing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    archive = tmp_path / "agent.snpack"
    SelfNomad.open(root).pack(archive, profile="specialist")
    staging = tmp_path / "unpacked"
    staging.mkdir()
    with tarfile.open(archive, "r:gz") as handle:
        extract = handle.extractall
        if "filter" in extract.__code__.co_varnames:
            extract(staging, filter="data")
        else:
            extract(staging)
    sidecar_path = staging / PACK_SIDECAR
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["skills"] = ["forged"]
    sidecar["self"]["name"] = "forged-name"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    forged = tmp_path / "forged.snpack"
    with tarfile.open(forged, "w:gz") as handle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                handle.add(path, arcname=path.relative_to(staging).as_posix())
    destination = tmp_path / "nope"
    with pytest.raises(PackError, match="does not match"):
        pull_pack(str(forged), destination)
    assert not destination.exists()


def test_publish_refuses_personal_without_explicit_confirm(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ConflictError, match="yes-personal"):
        publish_pack(root, tmp_path / "personal.snpack", profile="personal")


def test_publish_file_drop_passes_check(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    drop = tmp_path / "drop.snpack"
    summary = publish_pack(root, drop, profile="specialist")
    checked = SelfNomad.check_pack(drop)
    assert checked.content_digest == summary.content_digest
    assert drop.is_file()


def test_pull_by_index_name(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    archive = tmp_path / "named.snpack"
    SelfNomad.open(root).pack(archive, profile="specialist")
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"packages": [{"name": "demo", "pack": str(archive)}]}),
        encoding="utf-8",
    )
    destination = tmp_path / "from-index"
    summary = pull_pack("demo", destination, index_url=index.as_uri())
    assert summary.profile == "specialist"
    assert (destination / "self-nomad.yaml").is_file()
