"""End-to-end CLI intake workflow."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from self_nomad.application import SelfNomad
from self_nomad.cli import app
from self_nomad.filesystem import sha256_file
from tests.helpers import ensure_initial_commit, run_git

runner = CliRunner()


def _json_invoke(args: list[str], *, input_text: str | None = None) -> dict[str, object]:
    result = runner.invoke(app, args, input=input_text, catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def test_cli_intake_preview_submit_review_validate_approve_apply(
    isolated_env: Path, tmp_path: Path
) -> None:
    instance = SelfNomad.initialize(tmp_path / "agent", name="cli-intake")
    root = instance.repository.root
    ensure_initial_commit(root)
    before = sha256_file(root / "memory/MEMORY.md")
    content = "# Memory\r\n\r\n- Prefers concise status reports.\r\n"
    payload = {
        "schema_version": 1,
        "request_id": "openclaw:memory-update:e2e",
        "reason": "Record the user's preference for concise status reports.",
        "source": {
            "runtime": "openclaw",
            "agent_identifier": "primary",
            "correlation_id": "task-8421",
        },
        "operations": [
            {
                "kind": "replace",
                "path": "memory/MEMORY.md",
                "expected_before_sha256": before,
                "content": content,
            }
        ],
    }
    raw = json.dumps(payload)

    preview = _json_invoke(
        ["--repo", str(root), "--json", "intake", "--request", "-"],
        input_text=raw,
    )
    assert preview["ok"] is True
    assert preview["command"] == "intake"
    assert preview["result"]["eligible"] is True  # type: ignore[index]
    # Inline file content must not appear in the JSON result.
    serialized = json.dumps(preview["result"], sort_keys=True)
    assert "Prefers concise" not in serialized
    ops = preview["result"]["operations"]  # type: ignore[index]
    assert isinstance(ops, list) and "content" not in ops[0]  # type: ignore[index]

    request_file = tmp_path / "request.json"
    request_file.write_text(raw, encoding="utf-8")
    submitted = _json_invoke(
        ["--repo", str(root), "--json", "intake", "--request", str(request_file), "--submit"]
    )
    proposal_id = submitted["result"]["proposal_id"]  # type: ignore[index]
    assert submitted["result"]["reused"] is False  # type: ignore[index]
    assert submitted["result"]["status"] == "materialized"  # type: ignore[index]

    reused = _json_invoke(
        ["--repo", str(root), "--json", "intake", "--request", str(request_file), "--submit"]
    )
    assert reused["result"]["reused"] is True  # type: ignore[index]
    assert reused["result"]["proposal_id"] == proposal_id  # type: ignore[index]

    reviewed = _json_invoke(["--repo", str(root), "--json", "review", str(proposal_id)])
    assert reviewed["result"]["proposal"]["reason"].startswith("Record the user")  # type: ignore[index]
    assert reviewed["result"]["intake"]["request_id"] == "openclaw:memory-update:e2e"  # type: ignore[index]

    validated = _json_invoke(["--repo", str(root), "--json", "validate", str(proposal_id)])
    assert validated["result"]["status"] == "validated"  # type: ignore[index]

    approved = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "approve",
            str(proposal_id),
            "--identifier",
            "owner",
        ]
    )
    assert approved["result"]["status"] == "approved"  # type: ignore[index]

    applied = _json_invoke(["--repo", str(root), "--json", "apply", str(proposal_id)])
    assert applied["result"]["status"] == "applied"  # type: ignore[index]

    # Compare exact blob bytes on main (apply advances the target ref).
    completed = __import__("subprocess").run(
        ["git", "cat-file", "-p", "main:memory/MEMORY.md"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert completed.stdout == content.encode("utf-8")
    audit_paths = run_git(root, "ls-tree", "-r", "--name-only", "main").splitlines()
    has_audit = any(
        path.startswith(".self-nomad/audit/") and path.endswith(".json") for path in audit_paths
    )
    assert has_audit
    assert "memory/MEMORY.md" in audit_paths
