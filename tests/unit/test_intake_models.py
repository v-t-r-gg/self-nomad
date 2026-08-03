"""Unit tests for ProposalRequest contract and strict JSON loading."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import jsonschema
import pytest

from self_nomad.errors import (
    IntakeDuplicateKeyError,
    IntakeInvalidJsonError,
    IntakeInvalidUtf8Error,
    IntakeRequestTooLargeError,
    IntakeSchemaInvalidError,
    IntakeSchemaUnsupportedError,
)
from self_nomad.intake import (
    ProposalRequest,
    load_proposal_request,
    load_proposal_request_from_stream,
)
from self_nomad.intake.loader import load_proposal_request_from_path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "src/self_nomad/schemas/proposal-request-v1.schema.json"
DOCS_SCHEMA = ROOT / "docs/schema/proposal-request-v1.schema.json"


def _valid_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "request_id": "test:req:1",
        "reason": "Record a portable preference.",
        "source": {"runtime": "openclaw", "agent_identifier": "primary"},
        "operations": [
            {
                "kind": "replace",
                "path": "memory/MEMORY.md",
                "content": "# Memory\n\n- Prefers concise reports.\n",
            }
        ],
    }
    base.update(overrides)
    return base


def test_valid_request_round_trip_and_digest() -> None:
    payload = _valid_payload()
    raw = json.dumps(payload).encode("utf-8")
    request = load_proposal_request(raw)
    assert request.schema_version == 1
    assert request.canonical_digest() == request.canonical_digest()
    again = load_proposal_request(json.dumps(payload, sort_keys=True).encode())
    assert again.canonical_digest() == request.canonical_digest()


def test_crlf_content_bytes_preserved() -> None:
    content = "# Memory\r\n\r\n- Prefers concise status reports.\r\n"
    operations = [{"kind": "replace", "path": "memory/MEMORY.md", "content": content}]
    raw = json.dumps(_valid_payload(operations=operations)).encode()
    request = load_proposal_request(raw)
    assert request.operations[0].content_bytes() == content.encode("utf-8")
    assert "\r\n" in (request.operations[0].content or "")


def test_file_and_stdin_equivalence(tmp_path: Path) -> None:
    raw = json.dumps(_valid_payload()).encode("utf-8")
    path = tmp_path / "req.json"
    path.write_bytes(raw)
    from_file = load_proposal_request_from_path(path)
    from_stream = load_proposal_request_from_stream(BytesIO(raw))
    assert from_file.model_dump() == from_stream.model_dump()
    assert from_file.canonical_digest() == from_stream.canonical_digest()


def test_invalid_utf8_request_bytes() -> None:
    with pytest.raises(IntakeInvalidUtf8Error) as exc:
        load_proposal_request(b"\xff\xfe{not-json")
    assert exc.value.code == "INTAKE_INVALID_UTF8"


def test_duplicate_json_keys_rejected() -> None:
    raw = (
        b'{"schema_version":1,"schema_version":1,"request_id":"x","reason":"r",'
        b'"source":{"runtime":"r"},'
        b'"operations":[{"kind":"delete","path":"memory/MEMORY.md"}]}'
    )
    with pytest.raises(IntakeDuplicateKeyError) as exc:
        load_proposal_request(raw)
    assert exc.value.code == "INTAKE_DUPLICATE_KEY"


def test_unknown_fields_rejected() -> None:
    payload = _valid_payload(extra_field="nope")
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(json.dumps(payload).encode())


def test_unsupported_schema_version() -> None:
    payload = _valid_payload(schema_version=2)
    with pytest.raises(IntakeSchemaUnsupportedError) as exc:
        load_proposal_request(json.dumps(payload).encode())
    assert exc.value.code == "INTAKE_SCHEMA_UNSUPPORTED"


def test_oversized_request_envelope() -> None:
    raw = json.dumps(_valid_payload()).encode()
    with pytest.raises(IntakeRequestTooLargeError):
        load_proposal_request(raw, maximum_request_bytes=10)


def test_nul_and_control_characters_rejected() -> None:
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(
            json.dumps(_valid_payload(reason="bad\x00reason")).encode()
        )
    bad_ops = [{"kind": "replace", "path": "memory/MEMORY.md", "content": "x\x01y"}]
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(json.dumps(_valid_payload(operations=bad_ops)).encode())


def test_path_traversal_and_absolute_rejected() -> None:
    for path in ("../escape.md", "/etc/passwd", "memory\\win.md", "a/./b.md"):
        with pytest.raises(IntakeSchemaInvalidError):
            load_proposal_request(
                json.dumps(
                    _valid_payload(
                        operations=[{"kind": "replace", "path": path, "content": "x"}]
                    )
                ).encode()
            )


def test_delete_cannot_have_content_and_add_requires_content() -> None:
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(
            json.dumps(
                _valid_payload(
                    operations=[{"kind": "delete", "path": "memory/MEMORY.md", "content": "x"}]
                )
            ).encode()
        )
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(
            json.dumps(
                _valid_payload(operations=[{"kind": "add", "path": "memory/extra.md"}])
            ).encode()
        )


def test_sha256_must_be_lowercase_hex() -> None:
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(
            json.dumps(
                _valid_payload(
                    operations=[
                        {
                            "kind": "replace",
                            "path": "memory/MEMORY.md",
                            "content": "x",
                            "expected_after_sha256": "A" * 64,
                        }
                    ]
                )
            ).encode()
        )


def test_malformed_json() -> None:
    with pytest.raises(IntakeInvalidJsonError):
        load_proposal_request(b"{not-json")


def test_symlink_request_file_rejected(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(json.dumps(_valid_payload()), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request_from_path(link)


def test_public_intake_models_importable() -> None:
    assert ProposalRequest is not None


def test_schema_files_exist_and_validate_examples() -> None:
    assert SCHEMA_PATH.is_file()
    assert DOCS_SCHEMA.is_file()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False or "properties" in schema
    payload = _valid_payload()
    jsonschema.validate(payload, schema)
    # Package schema must match docs schema.
    assert SCHEMA_PATH.read_text(encoding="utf-8") == DOCS_SCHEMA.read_text(encoding="utf-8")


def test_committed_examples_validate_against_model_and_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    examples = sorted((ROOT / "examples/intake").glob("*.json"))
    assert examples, "expected example request files"
    for path in examples:
        raw = path.read_bytes()
        request = load_proposal_request(raw)
        assert request.schema_version == 1
        jsonschema.validate(json.loads(raw.decode("utf-8")), schema)


def test_schema_packaged_for_importlib_resources() -> None:
    from importlib.resources import files

    resource = files("self_nomad.schemas").joinpath("proposal-request-v1.schema.json")
    assert resource.is_file()
    data = json.loads(resource.read_text(encoding="utf-8"))
    assert data.get("title")


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "payload",
    [
        # add without content
        {
            **_valid_payload(),
            "operations": [{"kind": "add", "path": "memory/extra.md"}],
        },
        # replace without content
        {
            **_valid_payload(),
            "operations": [{"kind": "replace", "path": "memory/MEMORY.md"}],
        },
        # delete with content
        {
            **_valid_payload(),
            "operations": [
                {"kind": "delete", "path": "memory/MEMORY.md", "content": "x"}
            ],
        },
        # delete with after hash
        {
            **_valid_payload(),
            "operations": [
                {
                    "kind": "delete",
                    "path": "memory/MEMORY.md",
                    "expected_after_sha256": "a" * 64,
                }
            ],
        },
        # uppercase digest
        {
            **_valid_payload(),
            "operations": [
                {
                    "kind": "replace",
                    "path": "memory/MEMORY.md",
                    "content": "x",
                    "expected_after_sha256": "A" * 64,
                }
            ],
        },
        # short digest
        {
            **_valid_payload(),
            "operations": [
                {
                    "kind": "replace",
                    "path": "memory/MEMORY.md",
                    "content": "x",
                    "expected_after_sha256": "abcd",
                }
            ],
        },
        # nonhex digest
        {
            **_valid_payload(),
            "operations": [
                {
                    "kind": "replace",
                    "path": "memory/MEMORY.md",
                    "content": "x",
                    "expected_after_sha256": "g" * 64,
                }
            ],
        },
        # unknown nested field
        {
            **_valid_payload(),
            "operations": [
                {
                    "kind": "replace",
                    "path": "memory/MEMORY.md",
                    "content": "x",
                    "extra": 1,
                }
            ],
        },
        # invalid request id (space)
        {**_valid_payload(), "request_id": "bad id"},
        # invalid portable path (absolute)
        {
            **_valid_payload(),
            "operations": [
                {"kind": "replace", "path": "/etc/passwd", "content": "x"}
            ],
        },
        # invalid portable path (empty segment via trailing issues / special)
        {
            **_valid_payload(),
            "operations": [
                {"kind": "replace", "path": "memory\\win.md", "content": "x"}
            ],
        },
    ],
)
def test_json_schema_rejects_invalid_contracts(payload: dict[str, object]) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, _schema())


def test_pydantic_rejects_dotdot_path() -> None:
    with pytest.raises(IntakeSchemaInvalidError):
        load_proposal_request(
            json.dumps(
                _valid_payload(
                    operations=[{"kind": "replace", "path": "../escape.md", "content": "x"}]
                )
            ).encode()
        )
