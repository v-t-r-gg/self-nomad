# self-nomad

an agent's self, untethered from its runtime.

`self-nomad` is a local-first Python CLI for putting an AI agent's durable
identity, curated memory, and skills under safe Git version control. Import an
existing agent, review changes as typed proposals, and restore the portable
self on another machine or supported runtime without copying credentials or
session databases.

It is not an agent runtime and it does not call an LLM. It is the portability
and change-governance layer around the agents you already run.

## Development status

The deterministic repository foundation is under development. The current
slice supports repository initialization, discovery, manifest and policy
validation, safe repository-relative paths, and JSON CLI output.

```bash
uv sync
uv run self-nomad init /tmp/example --name example
uv run self-nomad --repo /tmp/example validate --strict
```

See [docs/repository-format.md](docs/repository-format.md) for the format and
[docs/threat-model.md](docs/threat-model.md) for the security boundary.

