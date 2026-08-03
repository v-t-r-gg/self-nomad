"""Durable intake receipts and content staging under private repository state."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from self_nomad.filesystem import atomic_write_bytes, atomic_write_text
from self_nomad.proposals.store import ProposalStore


class IntakeReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    request_id: str
    request_digest: str
    status: Literal["pending", "completed", "failed"]
    # Always set when a pending receipt is first written so retries never
    # allocate a second proposal UUID for the same request_id + digest.
    proposal_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


class IntakeStore:
    """Per-repository intake receipts and staged content files."""

    def __init__(self, proposal_store: ProposalStore) -> None:
        self.root = proposal_store.root / "i"
        self.receipts = self.root / "r"
        self.staging = self.root / "s"
        self.lock_path = self.root / "lock"

    def ensure_writable(self) -> None:
        """Create directories only when durable intake writes are required."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.receipts.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.staging.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def receipt_key(request_id: str) -> str:
        return hashlib.sha256(request_id.encode("utf-8")).hexdigest()

    def receipt_path(self, request_id: str) -> Path:
        return self.receipts / f"{self.receipt_key(request_id)}.json"

    def load_receipt(self, request_id: str) -> IntakeReceipt | None:
        path = self.receipt_path(request_id)
        if not path.is_file():
            return None
        return IntakeReceipt.model_validate_json(path.read_text(encoding="utf-8"))

    def save_receipt(self, receipt: IntakeReceipt) -> None:
        self.ensure_writable()
        receipt.updated_at = datetime.now(UTC)
        content = json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        atomic_write_text(self.receipt_path(receipt.request_id), content, mode=0o600)

    def staging_dir(self, request_digest: str) -> Path:
        self.ensure_writable()
        path = self.staging / request_digest
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def stage_content(self, request_digest: str, index: int, content: bytes) -> Path:
        directory = self.staging_dir(request_digest)
        path = directory / f"{index:04d}.bin"
        atomic_write_bytes(path, content, mode=0o600)
        return path

    def clear_staging(self, request_digest: str) -> None:
        directory = self.staging / request_digest
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
