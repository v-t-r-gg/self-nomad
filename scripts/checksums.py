#!/usr/bin/env python3
"""Write and verify GNU coreutils-style SHA256SUMS for dist artifacts.

Optionally detach-sign SHA256SUMS with GPG when a key is available or
``--gpg`` is passed. GitHub Artifact Attestations remain the primary signed
provenance path for tagged releases; this file is the local/offline digest.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKSUM_NAME = "SHA256SUMS"
SIGNATURE_NAME = "SHA256SUMS.asc"
SKIP_NAMES = {CHECKSUM_NAME, SIGNATURE_NAME}


class ChecksumError(RuntimeError):
    """Raised when checksum generation or verification fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_paths(dist_dir: Path) -> list[Path]:
    if not dist_dir.is_dir():
        raise ChecksumError(f"dist directory not found: {dist_dir}")
    artifacts = [
        path
        for path in sorted(dist_dir.iterdir())
        if path.is_file()
        and path.name not in SKIP_NAMES
        and not path.name.startswith(".")
        and not path.name.endswith(".asc")
        and (
            path.name.endswith(".whl")
            or path.name.endswith(".tar.gz")
        )
    ]
    if not artifacts:
        raise ChecksumError(f"no artifacts to checksum under {dist_dir}")
    return artifacts


def write_checksums(dist_dir: Path) -> Path:
    lines = [f"{sha256_file(path)}  {path.name}" for path in artifact_paths(dist_dir)]
    output = dist_dir / CHECKSUM_NAME
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def parse_checksums(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ChecksumError(f"invalid SHA256SUMS line {lineno}: {raw!r}")
        digest, name = parts
        if name in mapping:
            raise ChecksumError(f"duplicate checksum entry: {name}")
        mapping[name] = digest.lower()
    if not mapping:
        raise ChecksumError("SHA256SUMS is empty")
    return mapping


def verify_checksums(dist_dir: Path, sums_path: Path | None = None) -> None:
    listed = parse_checksums((sums_path or dist_dir / CHECKSUM_NAME).read_text(encoding="utf-8"))
    present = {path.name: path for path in artifact_paths(dist_dir)}
    missing = sorted(set(listed) - set(present))
    extra = sorted(set(present) - set(listed))
    if missing:
        raise ChecksumError(f"SHA256SUMS lists missing files: {missing}")
    if extra:
        raise ChecksumError(f"artifacts missing from SHA256SUMS: {extra}")
    mismatches: list[str] = []
    for name, expected in listed.items():
        actual = sha256_file(present[name])
        if actual != expected:
            mismatches.append(f"{name}: expected {expected} got {actual}")
    if mismatches:
        raise ChecksumError("checksum mismatch: " + "; ".join(mismatches))


def gpg_sign(sums_path: Path, *, key: str | None = None, required: bool = False) -> Path | None:
    gpg = shutil.which("gpg")
    if gpg is None:
        if required:
            raise ChecksumError("gpg is required but was not found on PATH")
        return None
    destination = sums_path.with_name(SIGNATURE_NAME)
    if destination.exists():
        destination.unlink()
    command = [gpg, "--batch", "--yes", "--detach-sign", "--armor", "-o", str(destination)]
    if key:
        command.extend(["--local-user", key])
    command.append(str(sums_path))
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        if required:
            raise ChecksumError((completed.stderr or completed.stdout or "gpg failed").strip())
        if destination.exists():
            destination.unlink()
        return None
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("action", choices=("write", "verify", "sign"))
    parser.add_argument("--gpg", action="store_true", help="require a GPG signature")
    parser.add_argument(
        "--gpg-key",
        default=os.environ.get("SELF_NOMAD_GPG_KEY", ""),
        help="GPG user id (or SELF_NOMAD_GPG_KEY)",
    )
    args = parser.parse_args(argv)
    dist_dir = args.dist.resolve()
    try:
        if args.action == "write":
            path = write_checksums(dist_dir)
            print(path)
        elif args.action == "verify":
            verify_checksums(dist_dir)
            print(f"OK  {dist_dir / CHECKSUM_NAME}")
        else:
            sums = dist_dir / CHECKSUM_NAME
            if not sums.is_file():
                write_checksums(dist_dir)
            signed = gpg_sign(
                sums,
                key=args.gpg_key or None,
                required=args.gpg,
            )
            if signed is None:
                print("GPG signature skipped (no usable key)")
            else:
                print(signed)
    except ChecksumError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
