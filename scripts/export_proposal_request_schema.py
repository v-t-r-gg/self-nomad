#!/usr/bin/env python3
"""Export or check the ProposalRequest v1 JSON Schema.

Writes the schema generated from the Pydantic model to package data and docs.
When ``--check`` is passed, exits non-zero if committed files differ.

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
PACKAGE_SCHEMA = ROOT / "src/self_nomad/schemas/proposal-request-v1.schema.json"
DOCS_SCHEMA = ROOT / "docs/schema/proposal-request-v1.schema.json"


def build_schema() -> dict[str, object]:
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


def render(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schema(text: str) -> None:
    for path in (PACKAGE_SCHEMA, DOCS_SCHEMA):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas match the Pydantic model without writing",
    )
    args = parser.parse_args(argv)
    text = render(build_schema())
    if args.check:
        mismatches: list[str] = []
        for path in (PACKAGE_SCHEMA, DOCS_SCHEMA):
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
    write_schema(text)
    print(f"wrote {PACKAGE_SCHEMA.relative_to(ROOT)}")
    print(f"wrote {DOCS_SCHEMA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
