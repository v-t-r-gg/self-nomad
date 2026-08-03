"""Integration tests for intake preview, submit, and idempotency."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from self_nomad.application import SelfNomad
from self_nomad.domain import ProposalRecord, ProposalStatus
from self_nomad.errors import (
    IntakeContentTooLargeError,
    IntakeContentUnsafeError,
    IntakeIdConflictError,
    IntakePolicyRejectedError,
)
from self_nomad.filesystem import sha256_file
from self_nomad.intake import load_proposal_request


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def committed_repository(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "agent", name="intake-agent")
    git(app.repository.root, "config", "user.name", "Test User")
    git(app.repository.root, "config", "user.email", "test@example.invalid")
    git(app.repository.root, "add", ".")
    git(app.repository.root, "commit", "-m", "initial")
    return app


def request_bytes(
    *,
    request_id: str = "openclaw:memory-update:1",
    content: str = "# Memory\n\n- Prefers concise status reports.\n",
    path: str = "memory/MEMORY.md",
    kind: str = "replace",
    expected_before: str | None = None,
    expected_after: str | None = None,
    runtime: str = "openclaw",
    reason: str = "Record the user's preference for concise status reports.",
) -> bytes:
    operation: dict[str, object] = {"kind": kind, "path": path}
    if kind != "delete":
        operation["content"] = content
    if expected_before is not None:
        operation["expected_before_sha256"] = expected_before
    if expected_after is not None:
        operation["expected_after_sha256"] = expected_after
    payload = {
        "schema_version": 1,
        "request_id": request_id,
        "reason": reason,
        "source": {
            "runtime": runtime,
            "agent_identifier": "primary",
            "correlation_id": "task-8421",
        },
        "operations": [operation],
    }
    return json.dumps(payload).encode("utf-8")


def test_preview_has_zero_durable_changes(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    intake = app.intake(state_root=state)
    head = git(app.repository.root, "rev-parse", "HEAD")
    request = load_proposal_request(request_bytes())
    preview = intake.preview(request)
    assert preview.eligible is True
    assert preview.risk == "low"
    assert git(app.repository.root, "rev-parse", "HEAD") == head
    assert not list(state.rglob("*.json"))


def test_submit_idempotent_retry_and_conflict(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    intake = app.intake(state_root=state)
    raw = request_bytes()
    request = load_proposal_request(raw)
    first = intake.submit(request)
    assert first.reused is False
    assert first.status is ProposalStatus.MATERIALIZED
    second = intake.submit(load_proposal_request(raw))
    assert second.reused is True
    assert second.proposal_id == first.proposal_id
    changed = request_bytes(content="# Memory\n\n- Different.\n")
    with pytest.raises(IntakeIdConflictError):
        intake.submit(load_proposal_request(changed))


def test_idempotent_after_process_restart(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    raw = request_bytes(request_id="restart:1")
    first = app.intake(state_root=state).submit(load_proposal_request(raw))
    # New service instance simulates process restart.
    second = app.intake(state_root=state).submit(load_proposal_request(raw))
    assert second.reused is True
    assert second.proposal_id == first.proposal_id


def test_concurrent_identical_submission(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    raw = request_bytes(request_id="concurrent:1")

    def once() -> str:
        result = app.intake(state_root=state).submit(load_proposal_request(raw))
        return str(result.proposal_id)

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: once(), range(4)))
    assert len(set(ids)) == 1


def test_secret_in_content_fails_before_proposal(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    secret = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/SENTINEL\n"
    request = load_proposal_request(request_bytes(content=secret, request_id="secret:1"))
    intake = app.intake(state_root=state)
    with pytest.raises(IntakePolicyRejectedError):
        intake.submit(request)
    assert intake.proposals.store.list() == []


def test_secret_like_provenance_rejected(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    raw = request_bytes(request_id="github_pat_abcdefghijklmnopqrstuvwxyz12")
    request = load_proposal_request(raw)
    with pytest.raises(IntakePolicyRejectedError):
        app.intake(state_root=tmp_path / "state").submit(request)


def test_crlf_hash_preserved_through_submit(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    content = "# Memory\r\n\r\n- Prefers concise status reports.\r\n"
    before = sha256_file(app.repository.root / "memory/MEMORY.md")
    raw = request_bytes(content=content, expected_before=before)
    result = app.intake(state_root=tmp_path / "state").submit(load_proposal_request(raw))
    record = app.proposals(state_root=tmp_path / "state").store.load(result.proposal_id)
    worktree = Path(record.worktree or "")
    assert (worktree / "memory/MEMORY.md").read_bytes() == content.encode("utf-8")


def test_before_hash_mismatch_marks_ineligible(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    raw = request_bytes(expected_before="0" * 64)
    preview = app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
    assert preview.eligible is False
    assert any(item.code == "INTAKE_BEFORE_MISMATCH" for item in preview.findings)


def test_after_hash_mismatch_rejected(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    raw = request_bytes(expected_after="0" * 64)
    with pytest.raises(IntakeContentUnsafeError):
        app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))


def test_old_proposal_record_without_intake_still_loads(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    service = app.proposals(state_root=state)
    source = tmp_path / "memory.md"
    source.write_text("# Memory\n\nlegacy\n", encoding="utf-8")
    from self_nomad.domain import FileOperation

    record = service.create(
        reason="legacy proposal",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    # Simulate pre-intake JSON without intake field.
    path = service.store.path_for(record.proposal.id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("intake", None)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    loaded = ProposalRecord.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.intake is None
    assert loaded.proposal.id == record.proposal.id


def test_pending_receipt_recovery_after_proposal_exists(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    intake = app.intake(state_root=state)
    raw = request_bytes(request_id="recover:1")
    result = intake.submit(load_proposal_request(raw))
    # Force receipt back to pending with proposal id present (crash window).
    receipt = intake.store.load_receipt("recover:1")
    assert receipt is not None
    receipt.status = "pending"
    intake.store.save_receipt(receipt)
    again = intake.submit(load_proposal_request(raw))
    assert again.reused is True
    assert again.proposal_id == result.proposal_id
    final = intake.store.load_receipt("recover:1")
    assert final is not None
    assert final.status == "completed"


def test_unicode_byte_count_enforced(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    # 3-byte UTF-8 characters; count is bytes not code points.
    content = "你" * 400_000  # 3-byte UTF-8 code points → 1_200_000 bytes > 1 MiB
    raw = request_bytes(content=content, request_id="unicode:1")
    with pytest.raises(IntakeContentTooLargeError):
        app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
