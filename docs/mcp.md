# Bounded MCP agent surface

self-nomad exposes a **local stdio-only** Model Context Protocol (MCP) server
for repository inspection and proposal intake. Approval, application, restore,
rejection, import, and cleanup remain operator-controlled CLI operations.

## Install

Base installations do not require the MCP SDK:

```bash
pip install self-nomad
self-nomad --version
```

Enable the server with the optional extra:

```bash
pip install 'self-nomad[mcp]'
# or from a development checkout:
uv sync --extra dev --extra mcp
```

If the MCP extra is missing, `self-nomad-mcp` prints a concise install
instruction on stderr and exits non-zero. Importing `self_nomad` and running
the ordinary CLI never import the MCP SDK.

## Run

```bash
self-nomad-mcp --repo /absolute/path/to/agent-self
```

`--repo` is **required** and must be an **absolute** path. MCP hosts often
launch servers from unpredictable working directories; the server never
infers the managed repository from the process CWD. The repository root is
resolved and validated once at startup and stays fixed for the process
lifetime. Tool inputs never accept a repository path.

## Transport boundary

| Channel | Use |
| --- | --- |
| stdout | MCP protocol framing only |
| stderr | Diagnostics and logs |

This slice supports **local stdio only**. There is no HTTP listener, no
network client, no telemetry, no remote Git, and no host or runtime config
mutation. Managed Git continues to disable hooks, disable prompting, and honor
existing timeouts.

Server identity:

- name: `self-nomad`
- version: package metadata (`self_nomad.__version__`)

## Tool registry (closed allow-list)

| Tool | Read-only | Destructive | Idempotent | Open world |
| --- | --- | --- | --- | --- |
| `self_nomad_repository_status` | yes | no | yes | no |
| `self_nomad_repository_validate` | yes | no | yes | no |
| `self_nomad_intake_preview` | yes | no | yes | no |
| `self_nomad_intake_submit` | no | no | yes (request id) | no |
| `self_nomad_proposal_list` | yes | no | yes | no |
| `self_nomad_proposal_get` | yes | no | yes | no |
| `self_nomad_proposal_validate` | no | no | yes (unchanged) | no |

### Which tools create local state

| Tool | State |
| --- | --- |
| status / validate (repo) / preview / list / get | none (empty proposal state does not create directories) |
| `self_nomad_intake_submit` | receipt, staged content, isolated proposal worktree |
| `self_nomad_proposal_validate` | advances `materialized → validated` when checks pass |

### Explicitly absent

The server does **not** expose tools for approve, apply, reject, restore,
import, cleanup, remote push, runtime/host configuration writes, arbitrary
file I/O, or command execution. Host tool filters (OpenClaw `toolFilter`,
Hermes `tools.include`) are an additional boundary; the server allow-list
remains authoritative.

## Result envelope

Successful and failed tool calls return structured content:

```json
{
  "schema_version": 1,
  "tool": "self_nomad_intake_preview",
  "ok": true,
  "result": {},
  "warnings": [],
  "errors": []
}
```

Errors carry stable codes (existing self-nomad codes plus MCP transport codes
such as `MCP_REPOSITORY_UNAVAILABLE`, `MCP_CONFIGURATION_ERROR`,
`MCP_INVALID_ARGUMENT`). Responses never include tracebacks, environment
variables, inline proposal content, absolute staging paths, raw receipts, or
unbounded Git output.

## Resource

```text
self-nomad://schemas/proposal-request/v1
```

Returns the packaged ProposalRequest v1 JSON Schema. Arbitrary repository
files are not exposed as resources. Prompts and interactive UI components are
out of scope for this slice.

## Idempotency and concurrency

- Intake submit is keyed by `request_id` and canonical digest (same as CLI).
- Concurrent identical submissions return the same proposal id.
- Client disconnect during submit leaves recoverable receipts.
- Sync tool bodies run via the SDK thread path so parallel read-only calls are
  not blocked indefinitely by one long Git operation; per-repository proposal
  and intake locks still serialize writers.

## Safety notes

- **No authentication** in local stdio mode. Trust the operator who configures
  the MCP process and the host that launches it.
- Why approval/apply stay outside MCP: agents must not advance the durable
  self branch without human review.
- Why fixed `--repo`: prevents confused-deputy selection of a repository via
  CWD or tool arguments.
- Why stdout purity: MCP framing corrupts if logs interleave on stdout.
- Host tool filters complement but do not replace the server allow-list.

## Host integrations

- [OpenClaw](mcp-openclaw.md)
- [Hermes](mcp-hermes.md)

Examples live under `examples/mcp/`.

## SDK

Optional dependency: official Python MCP SDK v2 (`mcp>=2,<3`). Locked release
and protocol compatibility are recorded in the delivery PR and ADR 0006.
