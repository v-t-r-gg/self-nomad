# ADR 0003: Canonical human-readable repository format

Status: accepted

Use a versioned root YAML manifest pointing to repository-relative Markdown,
YAML, and Agent Skills artifacts. Runtime-specific adapters report fidelity;
the canonical format does not claim semantic equivalence between runtimes.

