import re
import subprocess
from pathlib import Path

from self_nomad.errors import ConflictError
from self_nomad.filesystem import atomic_write_text
from self_nomad.repository import SelfRepository
from self_nomad.repository.layout import ARTIFACT_TEMPLATES, POLICY_TEMPLATE, manifest_template


class SelfNomad:
    def __init__(self, repository: SelfRepository) -> None:
        self.repository = repository

    @classmethod
    def open(cls, path: Path) -> "SelfNomad":
        return cls(SelfRepository.discover(path))

    @classmethod
    def initialize(
        cls,
        path: Path,
        *,
        name: str,
        description: str | None = None,
        initialize_git: bool = True,
    ) -> "SelfNomad":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}", name):
            raise ValueError("name contains unsupported characters")
        path = path.resolve()
        if path.exists() and any(path.iterdir()):
            raise ConflictError(f"destination is not empty: {path}")
        path.mkdir(parents=True, exist_ok=True)
        for directory in (
            "memory/daily",
            "memory/knowledge",
            "skills",
            "workflows",
            "evals/cases",
            "evals/fixtures",
            "policy",
            ".self-nomad/audit",
        ):
            (path / directory).mkdir(parents=True, exist_ok=True)
        atomic_write_text(path / "self-nomad.yaml", manifest_template(name, description))
        atomic_write_text(path / "policy/policy.yaml", POLICY_TEMPLATE)
        atomic_write_text(path / ".gitignore", ".self-nomad.local.yaml\n")
        for relative, content in ARTIFACT_TEMPLATES.items():
            atomic_write_text(path / relative, content)
        for keep in (
            "memory/daily/.gitkeep",
            "memory/knowledge/.gitkeep",
            "skills/.gitkeep",
            "workflows/.gitkeep",
            "evals/cases/.gitkeep",
            "evals/fixtures/.gitkeep",
            ".self-nomad/audit/.gitkeep",
        ):
            atomic_write_text(path / keep, "")
        if initialize_git:
            subprocess.run(
                ["git", "init", "--quiet", "--", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
                env={"GIT_TERMINAL_PROMPT": "0"},
            )
        return cls(SelfRepository(path))

