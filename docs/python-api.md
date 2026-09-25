# Python API

Supported programmatic entry points. Prefer these over private modules under
`self_nomad.proposals.store`, intake fault injectors, or MCP SDK internals.

## Install

```bash
pip install self-nomad
# optional MCP server package surface:
pip install 'self-nomad[mcp]'
```

## Entry points

```python
from pathlib import Path
from self_nomad import SelfNomad, __version__
from self_nomad.application import SelfNomad  # same public class

# Create or open
instance = SelfNomad.initialize(Path("/tmp/agent"), name="demo")
instance = SelfNomad.open(Path("/tmp/agent"))

instance.repository          # SelfRepository
instance.proposals()         # ProposalService
instance.intake()            # IntakeService
```

`__version__` reads installed package metadata (`0+unknown` in an uninstalled
source tree).

## Initialization and validation

```python
from pathlib import Path
from self_nomad import SelfNomad

root = Path("/tmp/agent-self")
app = SelfNomad.initialize(root, name="demo-agent")
result = app.repository.validate(strict=True)
assert result.valid
print(result.content_digest)
```

## Proposal lifecycle

```python
from self_nomad.domain import FileOperation

ops = [
    FileOperation(
        kind="replace",
        path="memory/MEMORY.md",
        content_source="/tmp/candidate-memory.md",
    )
]
service = app.proposals()
record = service.create(reason="Update memory", operations=ops)
print(service.unified_diff(record.proposal.id))
record = service.validate(record.proposal.id)
record = service.approve(record.proposal.id, identifier="operator")
record = service.apply(record.proposal.id)  # clean checked-out main is fine
print(service.list_records())
print(service.applied_history())
```

States: `draft` → `materialized` → `validated` → `approved` → `applied`
(plus `rejected`, `stale`, `failed`).

## Snapshot pack

```python
summary = app.pack(Path("/tmp/agent.snpack"), profile="specialist")
print(summary.content_digest, summary.skills, summary.omitted)
checked = SelfNomad.check_pack(Path("/tmp/agent.snpack"))
assert checked.content_digest == summary.content_digest
installed, loaded = SelfNomad.install_pack(
    Path("/tmp/agent.snpack"), Path("/tmp/agent-copy")
)
assert loaded.content_digest == summary.content_digest
assert installed.repository.validate(strict=True).valid
```

The archive has no `.git`. Specialist profile strips user profile and daily
memory; long-term memory requires `include_long_term_memory=True`.

## Intake preview and submit

```python
from self_nomad.intake import load_proposal_request

raw = Path("request.json").read_bytes()
request = load_proposal_request(raw)
intake = app.intake()
preview = intake.preview(request)   # zero durable writes
if preview.eligible:
    result = intake.submit(request)  # idempotent by request_id
    print(result.proposal_id, result.reused)
```

Approval and apply remain separate (`proposals()`), never automatic from intake.

## Adapters

```python
from self_nomad.adapters import default_registry
# kit sample (not registered):
# from self_nomad.adapters import ExampleFilesAdapter

registry = default_registry()
adapter = registry.get("hermes")  # or "openclaw"
detection = adapter.detect(hint=None)
plan = adapter.plan_import(detection.candidates[0], app.repository)
# plan.mappings / plan.exclusions — preview only until import --yes / restore --yes
```

CLI remains the usual operator path for confirmed import/restore. Application
helpers for restore transactions live behind adapter + application services
used by the CLI.

## MCP server (optional)

```python
from pathlib import Path
from self_nomad.mcp_server import build_server, EXPECTED_TOOL_NAMES

server = build_server(Path("/abs/path/to/agent-self"))
# server.run(transport="stdio")  # process entry uses self-nomad-mcp
assert len(EXPECTED_TOOL_NAMES) == 7
```

Importing `build_server` requires the `mcp` extra.

## Public vs internal

| Public | Internal (do not depend on) |
| --- | --- |
| `SelfNomad`, domain models, errors | Underscore MCP SDK members |
| `load_proposal_request`, intake models | Test-only crash injectors |
| Adapter registry / adapter `name` API | Exact private state directory layout for logic |
| Packaged JSON Schema resources | Undocumented CLI implementation details |

## Related docs

- [CLI reference](cli-reference.md)
- [Agent intake](agent-intake.md)
- [Architecture](architecture.md)
