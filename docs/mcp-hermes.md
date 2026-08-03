# Hermes + self-nomad MCP

Configure Hermes Agent to launch the bounded self-nomad MCP server over stdio.
self-nomad never edits `~/.hermes/config.yaml` automatically.

Official docs: [MCP (Model Context Protocol) | Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).

## Prerequisites

```bash
pip install 'self-nomad[mcp]'
which self-nomad-mcp
```

## Example configuration

See `examples/mcp/hermes.yaml`. Accepted keys (current Hermes docs):

```yaml
mcp_servers:
  self_nomad:
    command: "/absolute/path/to/self-nomad-mcp"
    args:
      - "--repo"
      - "/absolute/path/to/agent-self"
    tools:
      include:
        - self_nomad_repository_status
        - self_nomad_repository_validate
        - self_nomad_intake_preview
        - self_nomad_intake_submit
        - self_nomad_proposal_list
        - self_nomad_proposal_get
        - self_nomad_proposal_validate
      prompts: false
      resources: true
```

Notes:

- `tools.include` whitelists MCP tool names before Hermes registers them.
- `tools.prompts: false` disables prompt utility wrappers.
- `tools.resources: true` keeps the ProposalRequest schema resource utilities
  available when Hermes supports them for this session.
- Hermes prefixes registered tools as `mcp_<server>_<tool>`, for example
  `mcp_self_nomad_self_nomad_repository_status`. Prefer the host’s tool picker
  over hard-coding prefixed names in prompts.

## Operator commands

```bash
hermes mcp                # interactive management when available
hermes mcp catalog
hermes mcp configure self_nomad
```

In a running chat session:

```text
/reload-mcp
```

## Scope and diagnostics

- The server is bound to the fixed `--repo` path for its lifetime.
- Stdio diagnostics appear on the process stderr; Hermes does not pass the full
  shell environment into stdio servers—only configured `env` plus a safe
  baseline.
- Parallel tool calls: leave `supports_parallel_tool_calls` unset/false unless
  you have reviewed concurrent submit behavior for your deployment. Read-only
  tools are safe to parallelize at the self-nomad lock layer; submit is
  idempotent but still acquires intake locks.
