# OpenClaw + self-nomad MCP

Configure OpenClaw to launch the bounded self-nomad MCP server over stdio.
self-nomad never writes OpenClaw configuration automatically.

Official OpenClaw docs: [Connect MCP servers](https://docs.openclaw.ai/tools/mcp)
and [CLI mcp](https://docs.openclaw.ai/cli/mcp).

## Prerequisites

```bash
pip install 'self-nomad[mcp]'
# or: uv tool install 'self-nomad[mcp]'  (when published)
which self-nomad-mcp   # record the absolute path
```

Use a virtual-environment absolute path for the executable when the host does
not inherit your shell `PATH`:

```text
/home/you/.venv/bin/self-nomad-mcp
```

After publication, hosts may instead use `uvx`:

```json5
{
  command: "uvx",
  args: ["--from", "self-nomad[mcp]", "self-nomad-mcp", "--repo", "/abs/path/agent-self"]
}
```

## Example configuration

See `examples/mcp/openclaw.json5`. Shape:

```json5
{
  mcp: {
    servers: {
      self_nomad: {
        command: "/absolute/path/to/self-nomad-mcp",
        args: [
          "--repo",
          "/absolute/path/to/agent-self"
        ],
        toolFilter: {
          include: [
            "self_nomad_repository_status",
            "self_nomad_repository_validate",
            "self_nomad_intake_preview",
            "self_nomad_intake_submit",
            "self_nomad_proposal_list",
            "self_nomad_proposal_get",
            "self_nomad_proposal_validate"
          ]
        }
      }
    }
  }
}
```

`toolFilter.include` is defense-in-depth. The server already refuses to register
approve/apply/import/restore tools.

## Operator checks

```bash
openclaw mcp list
openclaw mcp show self_nomad
openclaw mcp doctor --probe
```

Reload or restart the OpenClaw gateway after editing config so the stdio process
is re-spawned with the new `--repo` and tool filter. Sandboxed sessions may
require an additional allowlist of MCP server names—follow current OpenClaw
sandbox policy for your deployment.

## Diagnostics

- self-nomad MCP logs and startup errors go to **stderr** of the stdio process.
- Protocol traffic stays on **stdout**.
- If tools are missing, confirm `toolFilter.include` spelling and that
  `self-nomad[mcp]` is installed for the configured `command`.
