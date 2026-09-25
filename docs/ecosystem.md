# Ecosystem position

self-nomad is a **standalone local-first product**. It puts one agent's
durable identity, curated memory, and skills under Git version control on a
machine the operator already trusts. It is not a runtime, not a model host,
and not a public registry.

## What this repository ships

- A versioned portable tree (`self-nomad.yaml` and referenced artifacts)
- Structural validation, proposal governance, and transactional restore
- Hermes and OpenClaw adapters (plus an unregistered authoring kit)
- File-to-file snapshot export/import (`pack` / `install`)
- Optional local stdio MCP for inspection and intake

See [repository-format.md](repository-format.md),
[runtime-portability.md](runtime-portability.md),
[compatibility.md](compatibility.md), and
[mcp.md](mcp.md).

## What a future registry may do

The separate product is
[portable-agent-registry](https://github.com/v-t-r-gg/portable-agent-registry).
It **consumes** this toolkit:

- validate a tree
- export a credential-free snapshot (`self-nomad pack`)
- import that snapshot into a new local repository (`self-nomad install`)
- restore into a supported runtime

self-nomad does not host, search, or authenticate to that index. Those
commands, if built, live in the registry. `pack` and `install` stay
file-to-file primitives on the operator machine.

Product boundary: [ADR 0007](decisions/0007-publishable-package-profile.md).
Concept notes (not this product): [docs/future/](future/).
