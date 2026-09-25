# Architecture and orchestration model

## Components

`app.shortener` owns URL validation, code allocation, resolution, and click aggregation. `app.storage` owns SQLite connections and schema initialization. `app.main` exposes HTTP contracts. `app.orchestration` owns the persisted workflow DAG, deterministic stage agents, scheduling, retries, safe stops, approvals, re-planning, and metrics. `app.cli` runs the server and local scenarios.

SQLite stores links and click events separately from workflow runs and their append-only event history. Stage artifacts remain structured JSON inside a run snapshot; event records capture transitions and output hashes for traceability.

## Control flow and gates

The execution graph is: intake → decomposition → design/security/test planning (independent concurrent branches) → synchronization → implementation artifacts → validation and documentation (independent concurrent branches) → release readiness → human approval. Stage data declares upstream dependencies and the graph is validated for unknown nodes and cycles at startup. A node runs only after all dependency nodes complete. Ambiguous intake pauses the run with clarification questions. Stage failure retries within a two-attempt bound; repeated failures produce a fallback record and safe stop. High-impact brownfield and all release-ready scenarios wait for a human decision. Approval must include a hash of the displayed release artifact.

Re-planning records the prior requirement hash, all prior stage outputs and any approval, invalidates the affected downstream graph, clears the current approval, and recomputes outputs. The current prototype invalidates the full graph for changed requirements; a future refinement can use artifact-level dependency hashes to invalidate only the minimal descendant set.

## Policy boundary

Agents return outputs; they do not make approval decisions or deploy. The service restricts destinations to HTTP(S), rejects URL credentials, and does not fetch user-supplied URLs. High-impact changes and all release transitions require explicit human approval. Local scenario output is a proposal/evidence bundle rather than a claim of verified arbitrary code changes.

## Decisions

- Local deterministic stages make the demo repeatable and inspectable without model credentials.
- SQLite makes setup simple, with a clear limit around concurrent multi-process use.
- The runner is intentionally local and synchronous; a production deployment would move scheduling to a durable queue and use leases/locking.
- The rollback artifact proposes operator-reviewed compensating steps instead of attempting automatic data reversal.
- No production deployment endpoint exists; approval marks a run complete for demo purposes only.
