"""Checksum write/verify helpers used by the release rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.checksums import (
    ChecksumError,
    parse_checksums,
    sha256_file,
    verify_checksums,
    write_checksums,
)


def test_write_and_verify_roundtrip(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "self_nomad-9.9.9-py3-none-any.whl"
    sdist = dist / "self_nomad-9.9.9.tar.gz"
    wheel.write_bytes(b"wheel-bytes")
    sdist.write_bytes(b"sdist-bytes")
    (dist / ".gitignore").write_text("*\n", encoding="utf-8")
    sums = write_checksums(dist)
    assert sums.name == "SHA256SUMS"
    text = sums.read_text(encoding="utf-8")
    assert sha256_file(wheel) in text
    assert "self_nomad-9.9.9-py3-none-any.whl" in text
    assert ".gitignore" not in text
    verify_checksums(dist)


def test_verify_detects_mismatch_and_extra(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "self_nomad-9.9.9.tar.gz"
    artifact.write_bytes(b"one")
    write_checksums(dist)
    artifact.write_bytes(b"two")
    with pytest.raises(ChecksumError, match="checksum mismatch"):
        verify_checksums(dist)
    extra = dist / "self_nomad-9.9.9-py3-none-any.whl"
    extra.write_bytes(b"x")
    write_checksums(dist)
    extra.unlink()
    with pytest.raises(ChecksumError, match="missing files"):
        verify_checksums(dist)


def test_parse_checksums_rejects_garbage() -> None:
    with pytest.raises(ChecksumError, match="invalid"):
        parse_checksums("not-a-digest  file\n")
