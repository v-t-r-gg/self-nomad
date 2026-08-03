# Agent proposal intake

Framework-neutral intake lets an AI agent submit proposed changes to a portable
self repository as strict JSON. Intake enters the existing Git-isolated
proposal lifecycle:

```text
preview → submit → review → validate → approve → apply
```

Submit creates and materializes a proposal. **Approval and application remain
separate explicit human (or policy-gated) operations.** Tree binding, declared
diff verification, stale detection, secret scanning, atomic ref update, and
audit records are unchanged.

## Trust boundary

| Allowed | Out of contract |
| --- | --- |
| Portable identity, memory, skills, and similar repository paths | Credentials, sessions, runtime DBs, caches, logs |
| Inline UTF-8 text content | Binary / base64 blobs, filesystem `content_source` paths |
| Provenance (runtime, agent id, correlation id) | Tokens, environment dumps, prompts as free-form bags |
| Preview + submit | Automatic approve/apply, remote push, command execution |

Agents never supply content paths. self-nomad stages bytes under private
per-repository state and builds ordinary `FileOperation` values internally.

## Request contract

Version 1 requests are defined by `ProposalRequest` and exported as:

- Package data: `self_nomad/schemas/proposal-request-v1.schema.json`
- Docs copy: `docs/schema/proposal-request-v1.schema.json`

Discover the package schema at runtime:

```python
from importlib.resources import files
schema = files("self_nomad.schemas").joinpath("proposal-request-v1.schema.json").read_text()
```

Regenerate or check consistency:

```bash
uv run python scripts/export_proposal_request_schema.py
uv run python scripts/export_proposal_request_schema.py --check
```

### Limits

| Limit | Default | Policy field |
| --- | --- | --- |
| Request envelope | 4 MiB | `limits.maximum_request_bytes` |
| Per-file content | 1 MiB | `limits.maximum_file_bytes` |
| Operations per proposal | 100 | `limits.maximum_proposal_files` |

Existing policy files omit `maximum_request_bytes` and receive the default.
Content size is measured after UTF-8 encoding. CRLF, LF, Unicode, and final
newlines from the JSON string are preserved.

## Python API

```python
from pathlib import Path
from self_nomad import SelfNomad
from self_nomad.intake import load_proposal_request

instance = SelfNomad.open(Path("./agent-self"))
intake = instance.intake()
request = load_proposal_request(Path("request.json").read_bytes())
preview = intake.preview(request)   # no durable state
result = intake.submit(request)     # creates/materializes proposal
```

## CLI

```bash
# Preview (default)
self-nomad --repo ./agent-self --json intake --request request.json

# Stdin
self-nomad --repo ./agent-self --json intake --request - < request.json

# Durable submit
self-nomad --repo ./agent-self --json intake --request request.json --submit
```

Continue with existing commands:

```bash
self-nomad --repo ./agent-self review PROPOSAL_ID
self-nomad --repo ./agent-self validate PROPOSAL_ID
self-nomad --repo ./agent-self approve PROPOSAL_ID --identifier HUMAN
# Target branch must not be checked out in any worktree.
git switch -c review-work
self-nomad --repo ./agent-self apply PROPOSAL_ID
```

JSON envelopes keep `schema_version`, `command`, `ok`, `result`, `warnings`,
and `errors`. Inline content is never echoed in success or error payloads.
Stable intake codes include `INTAKE_REQUEST_TOO_LARGE`, `INTAKE_INVALID_UTF8`,
`INTAKE_INVALID_JSON`, `INTAKE_DUPLICATE_KEY`, `INTAKE_SCHEMA_UNSUPPORTED`,
`INTAKE_SCHEMA_INVALID`, `INTAKE_CONTENT_TOO_LARGE`, `INTAKE_CONTENT_UNSAFE`,
`INTAKE_ID_CONFLICT`, `INTAKE_POLICY_REJECTED`, and `INTAKE_SUBMISSION_FAILED`.

## Idempotency

- Same `request_id` + same canonical digest → return existing proposal (`reused: true`).
- Same `request_id` + different digest → `INTAKE_ID_CONFLICT`.
- Concurrent identical submissions create one proposal.
- Receipts are durable under private repository state; recovery does not rely on process memory.

Canonical digests hash the validated semantic model with sorted keys, compact
JSON separators, and UTF-8 encoding. self-nomad timestamps are outside the digest.

## Provenance

Completed proposals may carry optional `intake` provenance on the proposal
record (`request_id`, `request_digest`, `runtime`, `agent_identifier`,
`correlation_id`). Pre-intake records omit the field and still load.

## Secrets and apply rules

High-confidence secret patterns are scanned on content and provenance during
preview/submit. Application still requires a detached or switched-away target
branch. Secret scanning is not general-purpose DLP.

## Runtime integration

Hermes and OpenClaw should emit the same `ProposalRequest` JSON toward their
canonical self-repository destinations (portable memory/identity/skills only).
Examples live in `examples/intake/`. Do not include sessions, credentials,
`BOOTSTRAP.md`, or runtime databases in intake content.

## Network

Intake performs no network I/O. Schema files and requests are local.
