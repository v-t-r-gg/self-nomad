"""Integration tests for intake preview, submit, idempotency, and target trees."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation, ProposalRecord, ProposalStatus
from self_nomad.errors import (
    IntakeContentTooLargeError,
    IntakeContentUnsafeError,
    IntakeIdConflictError,
    IntakePolicyRejectedError,
    IntakeRequestTooLargeError,
)
from self_nomad.filesystem import sha256_file
from self_nomad.intake import IntakeService, ProposalRequest, load_proposal_request
from self_nomad.intake.models import IntakeSource, ReplaceOperation


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
    target_branch: str | None = None,
    operations: list[dict[str, object]] | None = None,
) -> bytes:
    if operations is None:
        operation: dict[str, object] = {"kind": kind, "path": path}
        if kind != "delete":
            operation["content"] = content
        if expected_before is not None:
            operation["expected_before_sha256"] = expected_before
        if expected_after is not None:
            operation["expected_after_sha256"] = expected_after
        operations = [operation]
    payload: dict[str, object] = {
        "schema_version": 1,
        "request_id": request_id,
        "reason": reason,
        "source": {
            "runtime": runtime,
            "agent_identifier": "primary",
            "correlation_id": "task-8421",
        },
        "operations": operations,
    }
    if target_branch is not None:
        payload["target_branch"] = target_branch
    return json.dumps(payload).encode("utf-8")


def count_proposals(state: Path) -> int:
    records = list(state.rglob("p/*.json"))
    return len(records)


def test_preview_has_zero_durable_writes(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state_root = tmp_path / "state"
    assert not state_root.exists()
    head = git(app.repository.root, "rev-parse", "HEAD")
    status = git(app.repository.root, "status", "--porcelain")
    branches_before = git(app.repository.root, "branch")
    request = load_proposal_request(request_bytes())
    preview = app.intake(state_root=state_root).preview(request)
    assert preview.eligible is True
    assert preview.risk == "low"
    assert not state_root.exists()
    assert git(app.repository.root, "rev-parse", "HEAD") == head
    assert git(app.repository.root, "status", "--porcelain") == status
    assert git(app.repository.root, "branch") == branches_before


def test_submit_idempotent_retry_and_conflict(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    intake = app.intake(state_root=state)
    raw = request_bytes()
    first = intake.submit(load_proposal_request(raw))
    assert first.reused is False
    assert first.status is ProposalStatus.MATERIALIZED
    second = intake.submit(load_proposal_request(raw))
    assert second.reused is True
    assert second.proposal_id == first.proposal_id
    assert count_proposals(state) == 1
    changed = request_bytes(content="# Memory\n\n- Different.\n")
    with pytest.raises(IntakeIdConflictError):
        intake.submit(load_proposal_request(changed))
    assert count_proposals(state) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "pending_receipt",
        "staging",
        "proposal_record",
        "materialized",
        "before_completed_receipt",
        "completed_receipt",
    ],
)
def test_crash_windows_resume_single_proposal(tmp_path: Path, fault: str) -> None:
    from self_nomad.intake.service import InjectedCrash

    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    raw = request_bytes(request_id=f"crash:{fault}")
    request = load_proposal_request(raw)
    first = IntakeService(app.repository, state_root=state, fault_after=fault)
    with pytest.raises(InjectedCrash):
        first.submit(request)

    resumed = IntakeService(app.repository, state_root=state)
    result = resumed.submit(load_proposal_request(raw))
    assert result.status is ProposalStatus.MATERIALIZED
    if fault == "completed_receipt":
        assert result.reused is True

    assert count_proposals(state) == 1
    receipt = resumed.store.load_receipt(request.request_id)
    assert receipt is not None
    assert receipt.proposal_id == result.proposal_id
    assert receipt.status == "completed"
    record = resumed.proposal_store.load(result.proposal_id)
    assert record.status is ProposalStatus.MATERIALIZED
    assert record.worktree is not None
    assert Path(record.worktree).is_dir()
    assert record.branch is not None
    branches = git(app.repository.root, "branch", "--list", "self-nomad/proposal/*")
    assert branches.count(result.proposal_id.hex) == 1
    staging = resumed.store.staging / receipt.request_digest
    assert not staging.exists()
    with pytest.raises(IntakeIdConflictError):
        resumed.submit(
            load_proposal_request(
                request_bytes(request_id=request.request_id, content="other\n")
            )
        )


def test_idempotent_after_process_restart(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    raw = request_bytes(request_id="restart:1")
    first = app.intake(state_root=state).submit(load_proposal_request(raw))
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
    assert count_proposals(state) == 1


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


def test_preview_uses_target_branch_blob_not_checkout(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    root = app.repository.root
    # Branch tip has different MEMORY content from current checkout after switch.
    other = "# Memory\n\n- On feature branch only.\n"
    git(root, "checkout", "-b", "feature")
    (root / "memory/MEMORY.md").write_text(other, encoding="utf-8")
    git(root, "add", "memory/MEMORY.md")
    git(root, "commit", "-m", "feature memory")
    feature_hash = git(root, "rev-parse", "feature:memory/MEMORY.md")
    # Compute blob sha256 of feature content.
    import hashlib

    feature_sha = hashlib.sha256(other.encode()).hexdigest()
    git(root, "checkout", "main")
    main_text = (root / "memory/MEMORY.md").read_text(encoding="utf-8")
    assert main_text != other
    # Request targets feature with hash matching feature, not main checkout.
    raw = request_bytes(
        request_id="branch:feature",
        target_branch="feature",
        content="# Memory\n\n- Updated via intake.\n",
        expected_before=feature_sha,
    )
    preview = app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
    assert preview.eligible is True
    assert preview.target_branch == "feature"
    assert preview.base_commit == git(root, "rev-parse", "feature")
    # Matching main's current bytes would be wrong for feature target.
    main_sha = hashlib.sha256(main_text.encode()).hexdigest()
    assert main_sha != feature_sha
    assert feature_hash  # object exists


def test_preview_add_exists_and_missing_replace(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    add_exists = request_bytes(
        request_id="add:exists",
        operations=[{"kind": "add", "path": "memory/MEMORY.md", "content": "x\n"}],
    )
    preview = app.intake(state_root=state).preview(load_proposal_request(add_exists))
    assert preview.eligible is False
    assert any(item.code == "INTAKE_ADD_EXISTS" for item in preview.findings)

    missing = request_bytes(
        request_id="replace:missing",
        operations=[
            {"kind": "replace", "path": "memory/nope.md", "content": "x\n"},
        ],
    )
    preview2 = app.intake(state_root=state).preview(load_proposal_request(missing))
    assert preview2.eligible is False
    assert any(item.code == "INTAKE_TARGET_MISSING" for item in preview2.findings)


def test_preview_duplicate_paths_rejected(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    raw = request_bytes(
        request_id="dup:1",
        operations=[
            {"kind": "replace", "path": "memory/MEMORY.md", "content": "a\n"},
            {"kind": "replace", "path": "memory/MEMORY.md", "content": "b\n"},
        ],
    )
    preview = app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
    assert preview.eligible is False
    assert any(item.code == "INTAKE_DUPLICATE_PATH" for item in preview.findings)


def test_preview_rejects_symlink_in_target_tree(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    root = app.repository.root
    link = root / "memory" / "link.md"
    link.symlink_to("MEMORY.md")
    git(root, "add", "memory/link.md")
    git(root, "commit", "-m", "add symlink")
    raw = request_bytes(
        request_id="symlink:1",
        operations=[{"kind": "replace", "path": "memory/link.md", "content": "x\n"}],
    )
    preview = app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
    assert preview.eligible is False
    assert any(item.code == "INTAKE_TARGET_SYMLINK" for item in preview.findings)


def test_direct_request_enforces_maximum_request_bytes(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    policy_path = app.repository.root / "policy/policy.yaml"
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8").replace(
            "maximum_proposal_files: 100\n",
            "maximum_proposal_files: 100\n  maximum_request_bytes: 200\n",
        ),
        encoding="utf-8",
    )
    # Build a valid but large semantic request.
    content = "x" * 500
    request = ProposalRequest(
        schema_version=1,
        request_id="size:direct",
        reason="size check",
        source=IntakeSource(runtime="test"),
        operations=[ReplaceOperation(kind="replace", path="memory/MEMORY.md", content=content)],
    )
    with pytest.raises(IntakeRequestTooLargeError):
        app.intake(state_root=tmp_path / "state").preview(request)
    with pytest.raises(IntakeRequestTooLargeError):
        app.intake(state_root=tmp_path / "state").submit(request)


def test_old_proposal_record_without_intake_still_loads(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    service = app.proposals(state_root=state)
    source = tmp_path / "memory.md"
    source.write_text("# Memory\n\nlegacy\n", encoding="utf-8")
    record = service.create(
        reason="legacy proposal",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    path = service.store.path_for(record.proposal.id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("intake", None)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    loaded = ProposalRecord.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.intake is None
    assert loaded.proposal.id == record.proposal.id


def test_intake_audit_includes_provenance(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    raw = request_bytes(request_id="audit:prov:1")
    result = app.intake(state_root=state).submit(load_proposal_request(raw))
    service = app.proposals(state_root=state)
    service.validate(result.proposal_id)
    service.approve(result.proposal_id, identifier="owner")
    git(app.repository.root, "switch", "-c", "review-work")
    applied = service.apply(result.proposal_id)
    audit = git(
        app.repository.root,
        "show",
        f"main:.self-nomad/audit/{result.proposal_id}.json",
    )
    body = json.loads(audit)
    assert body["intake"]["request_id"] == "audit:prov:1"
    assert body["intake"]["request_digest"] == result.request_digest
    assert body["intake"]["runtime"] == "openclaw"
    assert "Prefers concise" not in audit
    assert "/s/" not in audit  # no staging path leakage
    assert applied.status is ProposalStatus.APPLIED


def test_pre_intake_apply_omits_intake_audit_field(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    state = tmp_path / "state"
    source = tmp_path / "memory.md"
    source.write_text("# Memory\n\nlegacy apply\n", encoding="utf-8")
    service = app.proposals(state_root=state)
    record = service.create(
        reason="legacy apply",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    service.validate(record.proposal.id)
    service.approve(record.proposal.id, identifier="owner")
    git(app.repository.root, "switch", "-c", "review-work")
    service.apply(record.proposal.id)
    audit = json.loads(
        git(app.repository.root, "show", f"main:.self-nomad/audit/{record.proposal.id}.json")
    )
    assert "intake" not in audit


def test_unicode_byte_count_enforced(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    content = "你" * 400_000  # 1_200_000 bytes > 1 MiB
    raw = request_bytes(content=content, request_id="unicode:1")
    with pytest.raises(IntakeContentTooLargeError):
        app.intake(state_root=tmp_path / "state").preview(load_proposal_request(raw))
