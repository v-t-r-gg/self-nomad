import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from self_nomad.errors import GitOperationError


@dataclass(frozen=True)
class GitResult:
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CommitPathEntry:
    """Inspection of a repository path at an exact commit (no checkout)."""

    kind: Literal["missing", "blob", "symlink", "tree", "other"]
    sha256: str | None = None
    object_id: str | None = None


class GitBackend:
    def __init__(self, root: Path, *, timeout: float = 30) -> None:
        self.root = root.resolve()
        self.timeout = timeout

    def _git_prefix(self) -> list[str]:
        # Disable hooks without relying on a POSIX-only path string.
        # Enable long paths on Windows so worktrees under deep user-state
        # directories do not fail with "$GIT_DIR too big".
        hooks_path = "NUL" if os.name == "nt" else "/dev/null"
        return [
            "git",
            "-c",
            f"core.hooksPath={hooks_path}",
            "-c",
            "core.longpaths=true",
            "-c",
            "core.autocrlf=false",
        ]

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_EDITOR": "true",
                "GIT_PAGER": "cat",
                "LC_ALL": "C",
            }
        )
        return environment

    def run(self, *arguments: str, cwd: Path | None = None) -> GitResult:
        try:
            completed = subprocess.run(
                [*self._git_prefix(), *arguments],
                cwd=cwd or self.root,
                env=self._environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitOperationError(f"Git command could not run: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise GitOperationError(f"git {arguments[0]} failed: {detail}")
        return GitResult(completed.stdout, completed.stderr)

    def run_bytes(self, *arguments: str, cwd: Path | None = None) -> bytes:
        try:
            completed = subprocess.run(
                [*self._git_prefix(), *arguments],
                cwd=cwd or self.root,
                env=self._environment(),
                check=False,
                capture_output=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitOperationError(f"Git command could not run: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            raise GitOperationError(f"git {arguments[0]} failed: {detail}")
        return completed.stdout

    def head(self, ref: str = "HEAD") -> str:
        return self.run("rev-parse", "--verify", ref).stdout.strip()

    def current_branch(self) -> str:
        return self.run("symbolic-ref", "--short", "HEAD").stdout.strip()

    def worktree_add(self, path: Path, branch: str, base: str) -> None:
        self.run("worktree", "add", "--quiet", "-b", branch, str(path), base)

    def commit_all(self, worktree: Path, message: str) -> str:
        self.run("add", "-A", "--", ".", cwd=worktree)
        self.run("commit", "--quiet", "-m", message, cwd=worktree)
        return self.run("rev-parse", "HEAD", cwd=worktree).stdout.strip()

    def commit_paths(self, worktree: Path, message: str, paths: list[str]) -> str:
        self.run("add", "--", *paths, cwd=worktree)
        self.run("commit", "--quiet", "-m", message, "--", *paths, cwd=worktree)
        return self.run("rev-parse", "HEAD", cwd=worktree).stdout.strip()

    def tree(self, commit: str) -> str:
        return self.run("rev-parse", f"{commit}^{{tree}}").stdout.strip()

    def is_clean(self, worktree: Path) -> bool:
        return not self.run(
            "status", "--porcelain=v1", "--untracked-files=all", cwd=worktree
        ).stdout

    def changed_paths(self, base: str, commit: str) -> dict[str, str]:
        output = self.run("diff-tree", "--no-commit-id", "--name-status", "-r", base, commit).stdout
        result: dict[str, str] = {}
        for line in output.splitlines():
            status, path = line.split("\t", 1)
            result[path] = status
        return result

    def checked_out_branches(self) -> set[str]:
        branches: set[str] = set()
        for line in self.run("worktree", "list", "--porcelain").stdout.splitlines():
            if line.startswith("branch refs/heads/"):
                branches.add(line.removeprefix("branch refs/heads/"))
        return branches

    def update_ref(self, branch: str, new: str, expected_old: str) -> None:
        self.run("update-ref", f"refs/heads/{branch}", new, expected_old)

    def remove_worktree(self, path: Path) -> None:
        self.run("worktree", "remove", "--force", str(path))

    def path_at_commit(self, commit: str, relative_path: str) -> CommitPathEntry:
        """Inspect ``relative_path`` at ``commit`` without checking out the tree.

        Uses ``git ls-tree`` / ``git cat-file`` object data only. Does not follow
        filesystem symlinks in the working tree.
        """
        listing = self.run("ls-tree", "--full-tree", commit, "--", relative_path).stdout
        lines = [line for line in listing.splitlines() if line.strip()]
        if not lines:
            return CommitPathEntry(kind="missing")
        # Exact path match only (ls-tree can return children for prefixes).
        for line in lines:
            meta, _, name = line.partition("\t")
            if name != relative_path:
                continue
            parts = meta.split()
            if len(parts) < 3:
                return CommitPathEntry(kind="other")
            mode, obj_type, object_id = parts[0], parts[1], parts[2]
            if obj_type == "tree":
                return CommitPathEntry(kind="tree", object_id=object_id)
            if obj_type != "blob":
                return CommitPathEntry(kind="other", object_id=object_id)
            if mode == "120000":
                return CommitPathEntry(kind="symlink", object_id=object_id)
            content = self.run_bytes("cat-file", "-p", object_id)
            digest = hashlib.sha256(content).hexdigest()
            return CommitPathEntry(kind="blob", sha256=digest, object_id=object_id)
        return CommitPathEntry(kind="missing")
