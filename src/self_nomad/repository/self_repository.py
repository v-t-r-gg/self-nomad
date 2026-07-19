import hashlib
import re
from pathlib import Path

from pydantic import ValidationError

from self_nomad.domain import Finding, ValidationResult
from self_nomad.errors import ManifestError, RepositoryNotFoundError
from self_nomad.filesystem import contained_path, sha256_file
from self_nomad.manifest import Manifest, load_manifest
from self_nomad.manifest.loader import load_yaml
from self_nomad.policy import Policy


class SelfRepository:
    SENSITIVE_NAMES = {
        ".env",
        "credentials.json",
        "auth-profiles.json",
        "id_rsa",
        "id_ed25519",
        "state.db",
    }
    SECRET_PATTERNS = (
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
        re.compile(rb"AKIA[0-9A-Z]{16}"),
    )

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @classmethod
    def discover(cls, start: Path) -> "SelfRepository":
        current = start.resolve()
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if (candidate / "self-nomad.yaml").is_file():
                return cls(candidate)
        raise RepositoryNotFoundError(f"no self-nomad.yaml found from {start}")

    @property
    def manifest_path(self) -> Path:
        return self.root / "self-nomad.yaml"

    def load_manifest(self) -> Manifest:
        return load_manifest(self.manifest_path)

    def validate(self, *, strict: bool = False) -> ValidationResult:
        findings: list[Finding] = []
        digest = hashlib.sha256()
        try:
            manifest = self.load_manifest()
            digest.update(sha256_file(self.manifest_path).encode())
        except ManifestError as exc:
            return ValidationResult(
                valid=False,
                findings=[Finding(severity="blocker", code="SN1001", message=str(exc))],
                content_digest=digest.hexdigest(),
                validator_versions={"repository": "1"},
            )

        policy: Policy | None = None
        try:
            policy_path = contained_path(self.root, manifest.policy, must_exist=True)
            policy = Policy.model_validate(load_yaml(policy_path))
            digest.update(sha256_file(policy_path).encode())
        except (ManifestError, ValidationError, OSError) as exc:
            findings.append(
                Finding(
                    severity="blocker",
                    code="SN1002",
                    message=f"invalid policy: {exc}",
                    path=manifest.policy,
                )
            )

        for relative in manifest.authoritative_paths():
            if relative == manifest.policy:
                continue
            try:
                path = contained_path(self.root, relative)
            except ManifestError as exc:
                findings.append(
                    Finding(severity="blocker", code="SN1101", message=str(exc), path=relative)
                )
                continue
            if not path.exists():
                findings.append(
                    Finding(
                        severity="error" if strict else "warning",
                        code="SN1102",
                        message="referenced artifact is missing",
                        path=relative,
                    )
                )
                continue
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                findings.append(
                    Finding(
                        severity="blocker",
                        code="SN1103",
                        message="artifact must be a regular file or directory",
                        path=relative,
                    )
                )
                continue
            files = [path] if path.is_file() else sorted(path.rglob("*"))
            for artifact_file in files:
                artifact_relative = artifact_file.relative_to(self.root).as_posix()
                if artifact_file.is_symlink() or (
                    artifact_file.exists()
                    and not artifact_file.is_file()
                    and not artifact_file.is_dir()
                ):
                    findings.append(
                        Finding(
                            severity="blocker",
                            code="SN1103",
                            message="artifact tree contains a symlink or special file",
                            path=artifact_relative,
                        )
                    )
                    continue
                if artifact_file.is_dir():
                    continue
                if artifact_file.name in self.SENSITIVE_NAMES or artifact_file.suffix == ".pem":
                    findings.append(
                        Finding(
                            severity="blocker",
                            code="SN1301",
                            message="sensitive filename is prohibited",
                            path=artifact_relative,
                        )
                    )
                if policy and artifact_file.stat().st_size > policy.limits.maximum_file_bytes:
                    findings.append(
                        Finding(
                            severity="error",
                            code="SN1201",
                            message="artifact exceeds maximum_file_bytes",
                            path=artifact_relative,
                        )
                    )
                if (
                    policy
                    and policy.validation.scan_for_secrets
                    and artifact_file.stat().st_size <= policy.limits.maximum_file_bytes
                ):
                    content = artifact_file.read_bytes()
                    if any(pattern.search(content) for pattern in self.SECRET_PATTERNS):
                        findings.append(
                            Finding(
                                severity="blocker",
                                code="SN1302",
                                message="high-confidence secret pattern detected",
                                path=artifact_relative,
                            )
                        )
                digest.update(artifact_relative.encode())
                digest.update(sha256_file(artifact_file).encode())

        invalid = {"error", "blocker"}
        return ValidationResult(
            valid=not any(item.severity in invalid for item in findings),
            findings=findings,
            content_digest=digest.hexdigest(),
            validator_versions={"repository": "1"},
        )
