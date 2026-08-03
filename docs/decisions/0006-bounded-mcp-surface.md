# 0006. Bounded local MCP agent surface

## Status

Accepted

## Context

Agents (OpenClaw, Hermes, and other MCP hosts) need a machine-readable way to
inspect a portable self repository and submit proposals without granting them
approval, apply, restore, or arbitrary filesystem authority.

The Model Context Protocol (MCP) is the emerging host-neutral tool interface.
self-nomad already has a strict ProposalRequest intake path and a closed
proposal lifecycle; the question is how much of that surface to expose over MCP.

## Decision

1. Ship an **optional** stdio MCP server (`self-nomad-mcp`) behind
   `pip install 'self-nomad[mcp]'` using the official Python MCP SDK v2
   (`mcp>=2,<3`).
2. Bind each server process to a **single absolute repository** via required
   `--repo`. Never accept repository paths in tool arguments or from CWD.
3. Expose exactly seven tools: repository status/validate, intake
   preview/submit, proposal list/get/validate.
4. Keep approve, apply, reject, restore, import, cleanup, remote Git, and
   configuration mutation **out of MCP**.
5. Return structured envelopes with stable error codes; route diagnostics to
   stderr only.
6. Expose the packaged ProposalRequest JSON Schema as one read-only resource.
7. Document OpenClaw and Hermes configuration examples without writing host
   config from self-nomad.

## Consequences

- Base installs stay free of the MCP SDK; installed base smoke asserts `mcp`
  and `mcp_types` are absent and `self-nomad-mcp` prints the install hint.
- Operators retain the human gate for durable branch advancement.
- Host tool filters are complementary, not authoritative. OpenClaw filters
  must also allow host-generated `resources_list` / `resources_read` if the
  schema resource should remain reachable.
- Recognized-tool argument failures return self-nomad envelopes with fixed
  public messages; unknown tools remain protocol-level MCP errors.
- Public error mapping never surfaces raw Git stderr, staging paths, or
  exception strings.
- HTTP/SSE/auth/OAuth remote deployment remain future work.
- Concurrent hosts on one repository still share local proposal locks and
  intake receipts.

## Alternatives considered

- Full CLI parity over MCP: rejected (approval/apply would bypass operator gate).
- Multi-repo tool parameter: rejected (confused deputy via path injection).
- Always-on MCP dependency: rejected (optionality and install weight).
