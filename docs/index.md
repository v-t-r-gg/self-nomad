# Documentation index

Maps for four readers: evaluators, operators, integrators, and contributors.
Source code, CLI help, Pydantic models, schemas, and tests are authoritative.

## Start here

| Document | Audience |
| --- | --- |
| [README](../README.md) | Everyone — two-minute product front door |
| [Getting started](getting-started.md) | Operators — first repository through apply |
| [Repository format](repository-format.md) | Operators / integrators — tree and policy |
| [Architecture](architecture.md) | Contributors — layers and lifecycle |

## Operate self-nomad

| Document | Topic |
| --- | --- |
| [Getting started](getting-started.md) | Init → propose → validate → approve → apply |
| [CLI reference](cli-reference.md) | Every command and option |
| [Repository format](repository-format.md) | Manifest, policy, hashing, constraints |
| [Runtime portability](runtime-portability.md) | Hermes and OpenClaw import/restore |
| [Agent intake](agent-intake.md) | ProposalRequest preview/submit and receipts |
| [MCP integration](mcp.md) | Local stdio server and host configs |
| [Security / threat model](threat-model.md) | Trust boundaries and residual risks |
| [Troubleshooting](troubleshooting.md) | Common failures and recovery |
| [Upgrading](upgrading.md) | RC layout and 0.2 development notes |

## Develop and extend

| Document | Topic |
| --- | --- |
| [Architecture](architecture.md) | Package layers, state, Git, MCP boundary |
| [Python API](python-api.md) | Supported programmatic entry points |
| [Adapter authoring](adapter-authoring.md) | Implementing another runtime adapter |
| [Contributing](../CONTRIBUTING.md) | Local verification and PR expectations |
| [Releasing](releasing.md) | Version-agnostic release procedure |
| [ADRs](decisions/) | Historical design decisions |

### MCP host guides

- [OpenClaw](mcp-openclaw.md)
- [Hermes](mcp-hermes.md)

### Schemas and examples

- [ProposalRequest JSON Schema](schema/proposal-request-v1.schema.json)
- [Intake examples](../examples/intake/)
- [MCP host examples](../examples/mcp/)
- [End-to-end intake walkthrough](../examples/e2e/README.md)

## Project meta

- [Changelog](../CHANGELOG.md)
- [Security policy](../SECURITY.md)
- [License](../LICENSE)
