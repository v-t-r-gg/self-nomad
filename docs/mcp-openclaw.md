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
            "self_nomad_proposal_validate",
            "resources_list",
            "resources_read"
          ]
        }
      }
    }
  }
}
```

### Native tools vs host resource utilities

| Name | Source | Purpose |
| --- | --- | --- |
| seven `self_nomad_*` tools | **Native** server registry | Inspection, intake, proposal review/validate |
| `resources_list` | OpenClaw-generated utility | List MCP resources (including the schema) |
| `resources_read` | OpenClaw-generated utility | Read `self-nomad://schemas/proposal-request/v1` |

The server’s native registry remains **exactly seven** tools. OpenClaw’s
`toolFilter.include` also applies to host-generated resource utilities, so
`resources_list` and `resources_read` must be listed if the schema resource
should stay available. They are not self-nomad tools and must not be counted
as part of the native allow-list.

`toolFilter.include` is defense-in-depth. The server already refuses to register
approve/apply/import/restore tools.

## Operator checks

```bash
openclaw mcp list
openclaw mcp show self_nomad
openclaw mcp doctor self_nomad --probe
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
- If the schema resource is missing, ensure `resources_list` and
  `resources_read` remain in the host filter.
