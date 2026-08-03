# ADR 0005: Agent proposal intake trust boundary

Status: accepted

## Context

Agents need a structured way to propose portable self-repository changes
without embedding runtime SDKs, automatic approval, or filesystem path
injection. The existing Git-isolated proposal lifecycle already provides tree
binding, validation, approval, and atomic apply.

## Decision

1. **Inline UTF-8 only.** Agents send text content in JSON. self-nomad stages
   exact UTF-8 bytes privately and never accepts caller `content_source` paths.
2. **Preview is free; submit materializes.** Durable proposals stop at
   `materialized`. Humans (or later policy gates) still approve and apply.
3. **Idempotent request IDs.** Canonical digests + per-repository receipts make
   retries and restarts safe; conflicting reuse fails closed.
4. **Human approval gate remains.** Intake does not approve or apply.
5. **Strict loader.** Duplicate keys, unknown fields, oversized envelopes, and
   invalid UTF-8 are rejected with stable codes.

## Consequences

- Runtime integrations share one contract and JSON Schema.
- Pre-intake proposal records remain loadable (optional provenance field).
- Binary artifacts, automatic apply, HTTP, and MCP are deferred.
