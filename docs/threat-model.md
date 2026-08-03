# Threat model

The protected assets are the user's durable agent content, credentials,
private operational state, repository history, and runtime targets. Inputs
from agents, manifests, repositories, runtimes, and Git remotes are untrusted.

The deterministic core prevents path traversal, rejects escaping symlinks,
loads YAML safely, limits content through policy, writes files atomically, and
does not execute repository-provided code. Credentials and session databases
are outside the product boundary.

Runtime adapters accept only explicit runtime roots, reject symlinked artifact
sources and targets, never inspect known credential/session stores as portable
content, and verify targets against the read-only plan immediately before
replacement. Replaced runtime files are copied to restrictive local state
before writes. Import staging is converted into typed, hash-bound proposal
operations rather than modifying the active checkout.

Agent intake accepts only strict JSON with inline UTF-8 content. Caller
filesystem content paths, credentials, session data, and automatic approval are
outside the intake contract. High-confidence secret patterns are rejected during
preview/submit before proposal creation.

The optional MCP server inherits the intake trust model and adds a local
process boundary: no authentication in stdio mode (the operator who configures
the host and `--repo` is trusted), fixed repository root for the process
lifetime, closed tool allow-list (no approve/apply/import/restore), sanitized
proposal payloads without inline content or staging paths, and stderr-only
diagnostics so protocol framing on stdout cannot leak stack traces. Host tool
filters are complementary; the server allow-list is authoritative.

Managed Git commands override `core.hooksPath` with a platform null device; repository and
global hooks therefore do not execute. Git clean/smudge/process filters remain
part of the user's trusted Git configuration. A repository using filters must
trust those filters to transform worktree bytes; proposal approval binds the
resulting complete Git tree and exact declared diff, not the filter program.

Git is an audit log, not a security boundary. Git history retains deleted
content. Structural validation cannot establish that an instruction is safe or
behaviorally beneficial. These are residual risks requiring review and careful
repository access control. Residual MCP risks include a compromised host
process spawning `self-nomad-mcp` against an unintended repository path, and
agents that can already write arbitrary files outside this server.
