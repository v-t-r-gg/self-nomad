import subprocess
from pathlib import Path

import pytest

from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation, ProposalStatus
from self_nomad.errors import ConflictError, ProposalStaleError


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def committed_repository(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "agent", name="example")
    git(app.repository.root, "config", "user.name", "Test User")
    git(app.repository.root, "config", "user.email", "test@example.invalid")
    git(app.repository.root, "add", ".")
    git(app.repository.root, "commit", "-m", "initial")
    return app


def test_proposal_is_isolated_then_applies_with_audit(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    root = app.repository.root
    original_head = git(root, "rev-parse", "HEAD")
    source = tmp_path / "memory.md"
    source.write_text("# Memory\n\nPortable fact.\n", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")

    record = service.create(
        reason="Add a curated portable fact",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )

    assert record.status is ProposalStatus.MATERIALIZED
    assert record.proposal.risk == "low"
    assert git(root, "rev-parse", "HEAD") == original_head
    assert (root / "memory/MEMORY.md").read_text() == "# Memory\n"
    proposed_memory = Path(record.worktree or "").joinpath("memory/MEMORY.md")
    assert proposed_memory.read_text() == source.read_text()

    service.validate(record.proposal.id)
    service.approve(record.proposal.id, identifier="test-user")
    git(root, "checkout", "-b", "work")
    applied = service.apply(record.proposal.id)

    assert applied.status is ProposalStatus.APPLIED
    assert git(root, "rev-parse", "refs/heads/main") == applied.applied_commit
    assert git(root, "symbolic-ref", "--short", "HEAD") == "work"
    assert (root / "memory/MEMORY.md").read_text() == "# Memory\n"
    assert not git(root, "status", "--porcelain")
    audit_name = f".self-nomad/audit/{record.proposal.id}.json"
    audit_content = git(root, "show", f"main:{audit_name}")
    assert record.proposal.reason in audit_content
    assert str(source) not in audit_content


def test_moved_target_marks_proposal_stale(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    root = app.repository.root
    source = tmp_path / "persona.md"
    source.write_text("# Persona\n\nChanged.\n", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")
    record = service.create(
        reason="Change persona",
        operations=[
            FileOperation(kind="replace", path="identity/persona.md", content_source=str(source))
        ],
    )
    assert record.proposal.risk == "high"
    service.validate(record.proposal.id)
    service.approve(record.proposal.id)
    (root / "README.md").write_text("concurrent\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "concurrent change")

    with pytest.raises(ProposalStaleError):
        service.apply(record.proposal.id)
    assert service.store.load(record.proposal.id).status is ProposalStatus.STALE


def test_before_hash_mismatch_fails_materialization(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    source = tmp_path / "replacement.md"
    source.write_text("replacement", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")
    with pytest.raises(ProposalStaleError):
        service.create(
            reason="Bad expected hash",
            operations=[
                FileOperation(
                    kind="replace",
                    path="memory/MEMORY.md",
                    expected_before_sha256="0" * 64,
                    content_source=str(source),
                )
            ],
        )


def test_apply_refuses_checked_out_target_branch(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    source = tmp_path / "memory.md"
    source.write_text("changed", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")
    record = service.create(
        reason="Change memory",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    service.validate(record.proposal.id)
    service.approve(record.proposal.id)
    with pytest.raises(ConflictError, match="checked out"):
        service.apply(record.proposal.id)
    assert not git(app.repository.root, "status", "--porcelain")


@pytest.mark.parametrize("mutation", ["untracked", "unstaged", "staged"])
def test_any_worktree_mutation_invalidates_approval(tmp_path: Path, mutation: str) -> None:
    app = committed_repository(tmp_path)
    source = tmp_path / "memory.md"
    source.write_text("changed", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")
    record = service.create(
        reason="Change memory",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    service.validate(record.proposal.id)
    service.approve(record.proposal.id)
    worktree = Path(record.worktree or "")
    if mutation == "untracked":
        (worktree / "rogue.txt").write_text("rogue", encoding="utf-8")
    else:
        (worktree / "README.md").write_text("rogue", encoding="utf-8")
        if mutation == "staged":
            git(worktree, "add", "README.md")
    git(app.repository.root, "checkout", "-b", "work")
    with pytest.raises(ProposalStaleError):
        service.apply(record.proposal.id)
    invalidated = service.store.load(record.proposal.id)
    assert invalidated.status is ProposalStatus.MATERIALIZED
    assert invalidated.approved_tree is None


def test_managed_git_commands_disable_repository_hooks(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    hook = app.repository.root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    source = tmp_path / "memory.md"
    source.write_text("changed", encoding="utf-8")
    record = app.proposals(state_root=tmp_path / "state").create(
        reason="Hook-safe change",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    assert record.status is ProposalStatus.MATERIALIZED


def test_committed_undeclared_change_invalidates_approval(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    source = tmp_path / "memory.md"
    source.write_text("changed", encoding="utf-8")
    service = app.proposals(state_root=tmp_path / "state")
    record = service.create(
        reason="Change memory",
        operations=[
            FileOperation(kind="replace", path="memory/MEMORY.md", content_source=str(source))
        ],
    )
    service.validate(record.proposal.id)
    service.approve(record.proposal.id)
    worktree = Path(record.worktree or "")
    (worktree / "rogue.txt").write_text("rogue", encoding="utf-8")
    git(worktree, "add", "rogue.txt")
    git(worktree, "commit", "-m", "undeclared")
    git(app.repository.root, "checkout", "-b", "work")
    with pytest.raises(ProposalStaleError):
        service.apply(record.proposal.id)
    assert service.store.load(record.proposal.id).status is ProposalStatus.MATERIALIZED
