import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from self_nomad.errors import GitOperationError


@dataclass(frozen=True)
class GitResult:
    stdout: str
    stderr: str


class GitBackend:
    def __init__(self, root: Path, *, timeout: float = 30) -> None:
        self.root = root.resolve()
        self.timeout = timeout

    def run(self, *arguments: str, cwd: Path | None = None) -> GitResult:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_EDITOR": "true",
                "GIT_PAGER": "cat",
                "LC_ALL": "C",
            }
        )
        try:
            completed = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", *arguments],
                cwd=cwd or self.root,
                env=environment,
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
