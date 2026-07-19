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

Git is an audit log, not a security boundary. Git history retains deleted
content. Structural validation cannot establish that an instruction is safe or
behaviorally beneficial. These are residual risks requiring review and careful
repository access control.
