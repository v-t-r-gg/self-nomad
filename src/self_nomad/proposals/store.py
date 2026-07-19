import hashlib
import json
from pathlib import Path
from uuid import UUID

from platformdirs import user_state_path

from self_nomad.domain import ProposalRecord
from self_nomad.errors import ProposalNotFoundError
from self_nomad.filesystem import atomic_write_text


class ProposalStore:
    def __init__(self, repository_root: Path, state_root: Path | None = None) -> None:
        repository_key = hashlib.sha256(str(repository_root.resolve()).encode()).hexdigest()[:24]
        base = state_root or user_state_path("self-nomad", appauthor=False)
        self.root = base / "repos" / repository_key
        self.records = self.root / "proposals"
        self.worktrees = self.root / "worktrees"
        self.lock_path = self.root / "lock"
        self.records.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.worktrees.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path_for(self, proposal_id: UUID) -> Path:
        return self.records / f"{proposal_id}.json"

    def save(self, record: ProposalRecord) -> None:
        content = json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        atomic_write_text(self.path_for(record.proposal.id), content, mode=0o600)

    def load(self, proposal_id: UUID) -> ProposalRecord:
        path = self.path_for(proposal_id)
        try:
            return ProposalRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProposalNotFoundError(f"proposal not found: {proposal_id}") from exc

    def list(self) -> list[ProposalRecord]:
        return [
            ProposalRecord.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.records.glob("*.json"))
        ]

