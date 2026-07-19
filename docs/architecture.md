# Architecture

The CLI translates terminal input and structured results. Application services
orchestrate use cases. Domain schemas, policy, validation, adapters, and the
self repository depend only on lower-level filesystem and Git infrastructure.
Adapters never run Git or decide authorization; the policy layer never performs
runtime writes.

The initial implementation covers repository initialization and deterministic
validation. Git proposals and runtime adapters will build on these boundaries.

