# Demo script

1. Start the API, open `/docs`, create a short link, resolve it, and inspect click analytics.
2. Run `python -m app.cli demo greenfield`. Point out parallel review artifacts, their synchronization dependency, generated API/schema/change artifacts, validation, metrics, and `awaiting_approval`.
3. Run `python -m app.cli demo brownfield`. Explain the compatibility review, high risk tier, rollback plan, and same human gate.
4. Run `python -m app.cli demo ambiguous`. Show the clarification list and safe stop before decomposition or implementation.
5. Run the greenfield demo with `--fail-stage implementation`. Show the two bounded attempts, fallback record, and safe-stopped state.
6. For an API run, inspect `/api/runs/{id}/events`, then approve or reject with actor and rationale. Re-plan with a changed requirement and inspect the preserved lineage and invalidated stages.

The implementation proposal artifacts are review outputs. They do not automatically edit a repository, run generated code, or deploy a release.
