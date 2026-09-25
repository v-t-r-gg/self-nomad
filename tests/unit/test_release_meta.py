"""Release metadata derived from packaging version and tags."""

from __future__ import annotations

import pytest

from scripts.release_meta import (
    assert_tag_matches_project,
    is_prerelease,
    project_version,
    tag_for_version,
    version_from_tag,
)


def test_project_version_is_pep440_like() -> None:
    version = project_version()
    assert version[0].isdigit()
    assert "unknown" not in version


def test_tag_roundtrip() -> None:
    version = project_version()
    assert version_from_tag(tag_for_version(version)) == version
    assert version_from_tag(version) == version


def test_prerelease_detection() -> None:
    assert is_prerelease("0.2.0rc1") is True
    assert is_prerelease("0.2.0.dev0") is True
    assert is_prerelease("0.2.0") is False


def test_assert_tag_matches_project() -> None:
    version = project_version()
    assert assert_tag_matches_project(f"v{version}") == version
    with pytest.raises(ValueError, match="does not match"):
        assert_tag_matches_project("v0.0.0")
