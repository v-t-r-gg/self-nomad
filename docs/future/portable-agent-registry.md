# Portable Agent Registry

> **Not a self-nomad product milestone.** This is a copy of the founding
> concept for a *separate* registry product so this CLI stays aware of the
> integration use case. The live repository is
> [v-t-r-gg/portable-agent-registry](https://github.com/v-t-r-gg/portable-agent-registry).
> self-nomad remains a standalone local-first CLI; the registry consumes
> validation and snapshot import/export. See
> [ADR 0007](../decisions/0007-publishable-package-profile.md) and
> [ecosystem.md](../ecosystem.md).
>
> Do not treat sections 9–13 below as self-nomad work.

*An Open Marketplace for Immutable, Portable AI Agent Packages*

Project Concept Document  •  August 2026

## 1. Vision

A public registry where anyone can publish, discover, and install complete, versioned AI agent packages. Each package contains the agent’s durable identity, curated memory, skills, and behavioral constraints in a clean, Git-based format. Packages travel between runtimes without credentials or session state. A portable reputation ledger travels with every package so other agents and humans can evaluate trustworthiness before use.

The site functions as the Hugging Face of portable agent selves: open, searchable, machine-readable first, and designed for both human browsers and agent-to-agent discovery.

## 2. Problem

Today’s agent sharing landscape is fragmented and incomplete:

- Most marketplaces lock agents to a single platform (GPT Store, Copilot Agent Store, vendor-specific builders).
- Personality-focused sites exist (SOULHUB, agentsoul.market) but remain small and limited to lightweight persona files.
- Full agent packages that include memory, skills, and governance history rarely travel cleanly between runtimes.
- Reputation is either absent or tied to a closed platform, so an agent that performs well in one environment carries no verifiable history elsewhere.
- Local-first and edge agents (phone, laptop, personal servers) lack a neutral place to publish and discover specialist packages.

## 3. Proposed Solution

Build an open registry that treats a self-nomad-style Git repository as the atomic unit of exchange. A published agent package is a content-addressed, credential-free snapshot containing:

- Identity – name, description, intended tasks, version, author
- Curated memory – durable facts, preferences, and learned patterns the agent carries
- Skills & tools – declarations of capabilities and tool interfaces
- Behavioral constraints – system prompt fragments, policy boundaries, safety rules
- Governance history – the proposal/approval trail that produced the current state
A portable reputation ledger attaches to each package. Signed outcome records (success, failure, cost, human corrections) accumulate over time and remain visible wherever the package is used.

## 4. Core Building Blocks

### 4.1 Self-Nomad Package Format

The registry adopts the self-nomad model as its native package format. self-nomad is a local-first Python toolkit that places an agent’s durable identity, curated memory, and skills under Git version control. Changes move through a typed proposal workflow (materialize → validate → approve → apply). Credentials and runtime session data never enter the repository.

A published package is simply a validated Git tree (or content-addressed snapshot of that tree) that any compatible runtime can restore transactionally.

### 4.2 Portable Reputation Ledger

Every package carries a cryptographically signed history of verified outcomes. Records include:

- Task category and success/failure
- Measured cost (tokens, latency, external spend)
- Human correction events
- Counterparty attestation (optional)
The ledger can begin as a simple signed feed mirrored by the registry and later evolve toward decentralized storage. Agents and humans query the ledger before installing or hiring a package.

## 5. Key Features

### Discovery

- Search by task, skill, domain, model family, or free-text description
- Filters for reputation score, number of verified runs, last update, license
- Machine-readable index (JSON/API) so other agents can discover packages without a browser

### Publishing

- CLI and web upload of a validated self-nomad repository
- Automatic extraction of identity, skill summary, and memory highlights for indexing
- Versioning that preserves the full proposal history

### Installation & Runtime Integration

- One-command restore into supported runtimes (Hermes, OpenClaw, and future adapters)
- Transactional apply with rollback on failure
- Clear separation: the package never contains API keys or owner credentials

### Reputation Surface

- Public score derived from verified outcome records
- Drill-down into individual attestations
- Ability for an agent or human to attach a new signed outcome after use

## 6. Target Users

#### Human Creators

Builders who tune agents for narrow, high-value tasks (invoice reconciliation, code review style, domain research, personal scheduling) and want those packages to travel beyond a single chat interface.

#### Human Consumers

Individuals and small teams who prefer to start from a proven specialist rather than prompting from scratch.

#### Local / Edge Agents

Phone- or laptop-resident agents that query the registry for the current best specialist for a sub-task, pull the package, and restore it locally or route work to it.

#### Platform Operators

Runtime providers that want a neutral source of high-quality, portable agent packages their users can import.

## 7. Market Context & Demand

Multiple agent marketplaces already operate. OpenAI’s GPT Store has over three million custom GPTs created and roughly 159,000 publicly listed. LobeHub lists more than 147,000 agents. Commercial marketplaces such as CustomAgent.app report thousands of listed agents and businesses served. Personality-focused sites (SOULHUB, agentsoul.market) demonstrate demand for portable personas even while remaining early-stage.

Enterprise and local-agent growth further increases the need. Hundreds of thousands of business agents already run in production. Forecasts show rapid expansion of the agentic AI market. Personal agents on devices continue to multiply, creating demand for packages that move cleanly between runtimes.

The open gap is a neutral, Git-native registry that treats full agent state (identity + memory + skills + governance) as a first-class, reputation-bearing package. Existing sites prove the desire to share and reuse; the proposed registry supplies the missing portability and verifiable history layer.

## 8. Competitive Landscape

Current offerings fall into several categories:

- Platform-locked stores – GPT Store, Microsoft Agent Store, Salesforce AgentExchange. High reach, low portability.
- Personality marketplaces – SOULHUB, agentsoul.market. Focused on souls/personas, still small.
- Commercial agent marketplaces – CustomAgent.app, AgentBazaar. Emphasize hiring and monetization.
- Open infrastructure – Hugging Face Spaces + agents.md, various GitHub collections. Strong openness, weak specialization in full agent packages.
No current platform combines a self-nomad-style immutable package format, portable reputation, and an open discovery surface designed for both humans and agents.

## 9. Minimum Viable Product

The first public release focuses on the smallest useful loop:

- Accept a validated self-nomad Git repository (or tarball of its tree) via CLI or simple web form.
- Extract and index identity, skill list, and short memory summary.
- Expose a searchable web UI and a machine-readable API.
- Allow any visitor to download the package and restore it with the self-nomad CLI.
- Attach a basic signed reputation feed (initially manual or CLI-submitted outcome records).
No payments, no complex governance UI, no multi-runtime adapters beyond the existing self-nomad ones. The goal is to prove that people will publish and that others will install.

## 10. Roadmap Sketch

- Phase 0 – Internal – Stabilize package contract with self-nomad, seed 10–20 high-quality packages, stand up read-only index.
- Phase 1 – Public MVP – Open publishing, search, download, basic reputation feed.
- Phase 2 – Agent-native discovery – Full API + MCP surface so local agents can query and pull packages autonomously.
- Phase 3 – Reputation depth – Richer attestation types, optional staking or skin-in-the-game signals, reputation graphs.
- Phase 4 – Ecosystem – Additional runtime adapters, optional monetization rails, federated mirrors.

## 11. Risks & Open Questions

- Cold-start – Early packages may be few. Mitigation: seed with strong internal and community packages; partner with existing self-nomad users.
- Quality & safety – Malicious or low-quality packages. Mitigation: validation on upload, community flagging, reputation as the primary filter.
- Format adoption – Other runtimes may not adopt the self-nomad package shape. Mitigation: keep the format simple and document clear adapters.
- Reputation gaming – Fake outcome records. Mitigation: start with signed, low-volume attestations; raise the cost of false claims over time.

## 12. Success Metrics (First Six Months)

- 50+ published packages from independent creators
- 500+ package installs / downloads
- At least one external runtime adapter beyond the initial set
- Measurable agent-to-agent discovery traffic via the API
- Positive qualitative feedback from local-agent builders

## 13. Immediate Next Steps

These steps belong to the **registry product**, not to this repository:

- Finalize the exact package manifest schema that the registry will index.
- Implement a minimal publish + search + download loop on top of existing self-nomad repositories.
- Seed the index with a first wave of high-quality packages.
- Expose a simple machine-readable endpoint so early agent experiments can query it.
- Document the end-to-end flow for both human publishers and agent consumers.

This registry turns the portable, immutable agent self into a first-class, discoverable object. It gives local and edge agents a neutral place to find specialists, and it gives creators a place to publish work that can outlive any single runtime.
