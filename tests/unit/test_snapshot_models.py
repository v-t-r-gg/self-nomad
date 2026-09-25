"""Pack profile and sidecar invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from self_nomad.snapshot.models import PACK_FORMAT, PackSummary
from self_nomad.snapshot.service import _omitted_fields, _skill_name


def test_specialist_omits_personal_classes_by_default() -> None:
    assert _omitted_fields("specialist", include_long_term_memory=False) == (
        "user_profile",
        "daily_memory",
        "long_term_memory",
    )
    assert _omitted_fields("specialist", include_long_term_memory=True) == (
        "user_profile",
        "daily_memory",
    )
    assert _omitted_fields("personal", include_long_term_memory=False) == ()


def test_skill_name_reads_front_matter(tmp_path: Path) -> None:
    skill = tmp_path / "lookup"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: lookup\n---\n# Lookup\n", encoding="utf-8")
    assert _skill_name(skill) == "lookup"
    empty = tmp_path / "anon"
    empty.mkdir()
    assert _skill_name(empty) == "anon"


def test_pack_summary_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PackSummary.model_validate(
            {
                "schema_version": 1,
                "pack_format": PACK_FORMAT,
                "profile": "specialist",
                "self": {"id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1", "name": "x"},
                "skill_format": "agent-skills",
                "policy": {
                    "approval_default": "required",
                    "scan_for_secrets": True,
                    "maximum_file_bytes": 1,
                },
                "content_digest": "ab",
                "created_at": "2026-08-17T00:00:00Z",
                "license": "MIT",
            }
        )
