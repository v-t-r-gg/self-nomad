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


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


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


def test_file_index_resolves_relative_pack_and_refuses_parent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    archive = tmp_path / "packages" / "demo.snpack"
    archive.parent.mkdir()
    SelfNomad.open(root).pack(archive, profile="specialist")
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"packages": [{"name": "demo", "pack": "packages/demo.snpack"}]}),
        encoding="utf-8",
    )
    destination = tmp_path / "from-relative"
    summary = pull_pack("demo", destination, index_url=index.as_uri())
    assert not (destination / "identity" / "user.md").exists()
    assert summary.profile == "specialist"

    index.write_text(
        json.dumps({"packages": [{"name": "demo", "pack": "../packages/demo.snpack"}]}),
        encoding="utf-8",
    )
    with pytest.raises(PackError, match="escapes"):
        pull_pack("demo", tmp_path / "escaped", index_url=index.as_uri())
    assert not (tmp_path / "escaped").exists()


def test_https_index_resolves_relative_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    archive = tmp_path / "named.snpack"
    SelfNomad.open(root).pack(archive, profile="specialist")
    index_url = "https://example.test/registry/index.json"
    pack_url = "https://example.test/registry/packages/demo/1.0.0/demo.snpack"
    index = json.dumps(
        {"packages": [{"name": "demo", "pack": "packages/demo/1.0.0/demo.snpack"}]}
    ).encode()
    seen: list[str] = []

    def fake_urlopen(url: str, timeout: int = 60) -> _Body:
        seen.append(url)
        if url == index_url:
            return _Body(index)
        if url == pack_url:
            return _Body(archive.read_bytes())
        raise AssertionError(url)

    monkeypatch.setattr("self_nomad.hub.client.urlopen", fake_urlopen)
    destination = tmp_path / "from-https"
    summary = pull_pack("demo", destination, index_url=index_url)
    assert seen == [index_url, pack_url]
    assert summary.profile == "specialist"
    assert not (destination / "identity" / "user.md").exists()


def test_https_index_refuses_parent_without_fetching_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_url = "https://example.test/registry/index.json"
    index = json.dumps({"packages": [{"name": "demo", "pack": "../demo.snpack"}]}).encode()

    def fake_urlopen(url: str, timeout: int = 60) -> _Body:
        if url == index_url:
            return _Body(index)
        raise AssertionError(url)

    monkeypatch.setattr("self_nomad.hub.client.urlopen", fake_urlopen)
    with pytest.raises(PackError, match="escapes"):
        pull_pack("demo", tmp_path / "nope", index_url=index_url)
    assert not (tmp_path / "nope").exists()
