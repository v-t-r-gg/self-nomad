# Ecosystem position

self-nomad is a **standalone local-first product**. It puts one agent's
durable identity, curated memory, and skills under Git version control on a
machine the operator already trusts. It is not a runtime, not a model host,
and not a public registry.

## What this repository ships

- A versioned portable tree (`self-nomad.yaml` and referenced artifacts)
- Structural validation, proposal governance, and transactional restore
- Hermes and OpenClaw adapters (plus an unregistered authoring kit)
- File-to-file snapshot commands: `pack`, `pack --check`, `install`
- Optional local stdio MCP for inspection and intake

See [repository-format.md](repository-format.md),
[snapshot.md](snapshot.md),
[runtime-portability.md](runtime-portability.md),
[compatibility.md](compatibility.md), and
[mcp.md](mcp.md).

## What a future registry may do

The separate product is
[portable-agent-registry](https://github.com/v-t-r-gg/portable-agent-registry).
It **consumes** this toolkit. The commands are the same on both sides of the
boundary:

- `self-nomad pack` — write a `self-nomad-pack-v1` snapshot (not a Git clone)
- `self-nomad pack --check` — verify that archive
- `self-nomad install` — import it into a new local repository
- `self-nomad validate --strict` — structural validation the check and install paths run
- `self-nomad restore` — copy mapped files into Hermes or OpenClaw

The unit of exchange is the snapshot. Proposal receipts and working Git
history are not package contents. self-nomad does not host, search, publish,
or authenticate to that index. Those commands, if built, live in the registry.

Product boundary: [ADR 0007](decisions/0007-publishable-package-profile.md).
Concept notes (not this product): [docs/future/](future/).
