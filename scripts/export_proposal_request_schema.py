#!/usr/bin/env python3
"""Export or check JSON Schemas generated from Pydantic models.

Writes ProposalRequest v1 and the self-nomad-pack-v1 sidecar schema to package
data and docs. When ``--check`` is passed, exits non-zero if committed files differ.

Usage::

    uv run python scripts/export_proposal_request_schema.py
    uv run python scripts/export_proposal_request_schema.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PROPOSAL = ROOT / "src/self_nomad/schemas/proposal-request-v1.schema.json"
DOCS_PROPOSAL = ROOT / "docs/schema/proposal-request-v1.schema.json"
PACKAGE_PACK = ROOT / "src/self_nomad/schemas/self-nomad-pack-v1.schema.json"
DOCS_PACK = ROOT / "docs/schema/self-nomad-pack-v1.schema.json"


def build_proposal_schema() -> dict[str, object]:
    from self_nomad.intake.models import ProposalRequest

    schema = ProposalRequest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://github.com/v-t-r-gg/self-nomad/schemas/proposal-request-v1.schema.json"
    schema["title"] = "self-nomad ProposalRequest v1"
    schema["description"] = (
        "Framework-neutral agent intake request for proposing changes to a "
        "portable self repository. Inline content is UTF-8 text only; "
        "filesystem content_source paths are not accepted."
    )
    return schema


def build_pack_schema() -> dict[str, object]:
    from self_nomad.snapshot.models import PackSummary

    schema = PackSummary.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://github.com/v-t-r-gg/self-nomad/schemas/self-nomad-pack-v1.schema.json"
    schema["title"] = "self-nomad pack sidecar v1"
    schema["description"] = (
        "Additive self-nomad.pack.json sidecar for a self-nomad-pack-v1 archive. "
        "It does not widen repository schema_version 1. License, authors, package "
        "version, and namespace are not fields of this object."
    )
    return schema


def render(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def schemas() -> list[tuple[Path, Path, str]]:
    return [
        (PACKAGE_PROPOSAL, DOCS_PROPOSAL, render(build_proposal_schema())),
        (PACKAGE_PACK, DOCS_PACK, render(build_pack_schema())),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas match the Pydantic models without writing",
    )
    args = parser.parse_args(argv)
    documents = schemas()
    if args.check:
        mismatches: list[str] = []
        for package, docs, text in documents:
            for path in (package, docs):
                if not path.is_file():
                    mismatches.append(f"missing {path.relative_to(ROOT)}")
                    continue
                if path.read_text(encoding="utf-8") != text:
                    mismatches.append(f"stale {path.relative_to(ROOT)}")
        if mismatches:
            print("schema check failed:", "; ".join(mismatches), file=sys.stderr)
            print("run: uv run python scripts/export_proposal_request_schema.py", file=sys.stderr)
            return 1
        print("schema check OK")
        return 0
    for package, docs, text in documents:
        for path in (package, docs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
