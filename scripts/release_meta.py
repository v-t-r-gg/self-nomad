#!/usr/bin/env python3
"""Release metadata helpers derived from pyproject.toml and git tags."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:\.dev[0-9]+|rc[0-9]+)?$")


def project_version(root: Path = ROOT) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(data["project"]["version"])
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"unsupported project version: {version!r}")
    return version


def tag_for_version(version: str) -> str:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"unsupported version: {version!r}")
    return f"v{version}"


def version_from_tag(tag: str) -> str:
    raw = tag[1:] if tag.startswith("v") else tag
    if not VERSION_RE.fullmatch(raw):
        raise ValueError(f"unsupported release tag: {tag!r}")
    return raw


def is_prerelease(version: str) -> bool:
    return "rc" in version or ".dev" in version


def assert_tag_matches_project(tag: str, root: Path = ROOT) -> str:
    expected = project_version(root)
    found = version_from_tag(tag)
    if found != expected:
        raise ValueError(f"tag {tag!r} does not match project.version {expected!r}")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "action",
        choices=("version", "tag", "prerelease", "check-tag"),
    )
    parser.add_argument("--tag", default="")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.action == "version":
            print(project_version(root))
        elif args.action == "tag":
            print(tag_for_version(project_version(root)))
        elif args.action == "prerelease":
            print("true" if is_prerelease(project_version(root)) else "false")
        else:
            if not args.tag:
                raise ValueError("--tag is required for check-tag")
            print(assert_tag_matches_project(args.tag, root))
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
