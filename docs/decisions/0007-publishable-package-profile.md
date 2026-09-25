# ADR 0007: Standalone product and publishable package profile

Status: accepted

## Context

self-nomad is a local-first toolkit for putting one agent's durable identity,
curated memory, and skills under Git version control. A separate concept —
an open registry of portable agent packages — may later consume that format.

Those are different products:

- This repository governs and moves a self on a trusted operator machine.
- A registry would host, search, and distribute many untrusted packages.

Proposal records, intake receipts, and restore backups already live outside
the portable tree ([ADR 0004](0004-local-state.md)). The threat model excludes
remote push from apply and remote MCP transports
([ADR 0006](0006-bounded-mcp-surface.md), [threat-model.md](../threat-model.md)).
Git history retains deleted content ([SECURITY.md](../../SECURITY.md)).

Without an explicit boundary, registry work would land in this tree and the
default personal layout (`identity/user.md`, daily memory, long-term memory)
would be treated as a public package.

## Decision

1. **self-nomad stays a standalone local product.** This repository does not
   host, index, search, authenticate, or operate a marketplace. Discovery,
   reputation, payments, and remote package APIs belong in a separate
   repository if they are built at all.

2. **A registry is a consumer, not a feature.** If a registry exists, it uses
   self-nomad the same way any other integrator would: validate a tree, export
   a credential-free snapshot, import that snapshot, restore into a runtime.
   self-nomad does not grow publish-to-hub or search-the-hub commands as
   product identity. Optional later clients, if any, stay out of the core CLI.

3. **The portable unit is a validated tree, not working Git history.** A
   future local export primitive writes a content-addressed snapshot of
   authoritative artifacts plus a machine-readable summary (identity, skill
   names, policy highlights, content digest). Import writes a new local
   repository and validates before the tree is trusted. Author `.git` history
   is not the default package. The commands are `self-nomad pack`,
   `self-nomad pack --check`, `self-nomad install`,
   `self-nomad validate --strict`, and `self-nomad restore`.

4. **Personal self and specialist package are different publish sets.** The
   default repository remains a personal agent self. A specialist snapshot
   must not include `user_profile` or daily memory by default. Long-term
   memory is not a dump: only facts the operator explicitly allow-lists belong
   in a shareable snapshot. Credentials, sessions, and runtime databases stay
   excluded.

5. **Governance history stays local.** Proposal records, worktrees, and
   intake receipts remain platform state ([ADR 0004](0004-local-state.md)).
   They do not become portable package contents. A registry that wants an
   audit trail owns that concern; Git log is not a package feature.

6. **Schema version 1 stays locked.** License, authors, package version,
   tasks, and tags are not silently added to `self-nomad.yaml`. An additive
   sidecar or an explicit schema bump requires its own change. Until then,
   `self.id`, `self.name`, and `self.description` plus content paths are the
   indexable identity.

7. **Untrusted snapshots fail closed.** Import validation is the gate, not a
   courtesy after checkout. Repository-provided tests and scripts are never
   executed ([repository-format.md](../repository-format.md)). Secret scanning
   remains high-confidence only, not general DLP.

8. **MCP stays local and single-repo.** The stdio server does not grow
   remote discovery, download, or restore tools.

## Consequences

- Contributors treat [docs/future/](../future/) as out-of-product notes, not
  a backlog for this CLI. The registry product lives at
  [v-t-r-gg/portable-agent-registry](https://github.com/v-t-r-gg/portable-agent-registry).
- `pack`, `pack --check`, `install`, `validate --strict`, and `restore` are
  the registry-facing commands. A registry CI job calls them rather than
  reimplementing validation.
- Sharing a live working clone remains a manual, operator-trusted path and is
  not a publishable package.

## Alternatives considered

- **Monorepo with a registry service:** rejected. Different trust model,
  stack, release cadence, and failure mode. Would fight ADRs 0004 and 0006.
- **Hub client commands in the core CLI:** rejected. The registry should
  streamline import/export by invoking local primitives, not by turning
  self-nomad into a marketplace client.
- **Publish the working Git repository:** rejected. History retains deleted
  content and personal artifacts.
- **Embed proposal receipts in the tree so packages carry governance:**
  rejected. Contradicts ADR 0004 and leaks local operator identifiers.

## Implementation notes

`self-nomad pack` writes a gzip tar of a validated tree plus additive
`self-nomad.pack.json`. `self-nomad install` extracts to staging, validates,
then writes a new local repository. Specialist is the default pack profile
(strips `user_profile` and daily memory; long-term memory is opt-in).
Namespace (`author/name`) is still deferred.

## Addendum (1.4.0): checked-pack transport

Decision 2 still stands. This repository does not host, search, or
authenticate to a marketplace. `self-nomad hub pull` and
`self-nomad hub publish` are a file transport in `self_nomad.hub`, not a
marketplace client and not an MCP tool.

- `hub pull` resolves a `.snpack` path, URL, or index name, runs
  `pack --check`, then `install`. The check is not optional. A failing check
  does not write the destination.
- `hub publish` writes a specialist pack (a personal pack requires
  `--yes-personal`), runs `pack --check`, and leaves that file for a human
  to commit under the registry's `packages/` tree. There is no upload API.
- A working Git clone is never the payload.
- The earlier rejection of "hub client commands in the core CLI" was about
  search, accounts, and authentication. These two verbs do none of those.
