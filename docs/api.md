# HTTP API reference

Interactive OpenAPI schema is available at `/docs` while the app is running.

## Short links

### `POST /api/links`

Request: `{"url":"https://example.com/path","alias":"optional-alias","expires_at":"optional ISO-8601 timestamp"}`. Returns `201` with `code`, `short_url`, normalized `url`, `created_at`, and `expires_at`. Aliases are optional and must be 3-32 ASCII letters, digits, `_`, or `-`.

### `GET /{code}`

Returns `307` to the stored HTTP(S) destination and records a click. Returns `404` for unknown codes and `410` for expired or disabled links.

### `POST /api/links/{code}/disable`

Disables an existing code; subsequent resolution returns `410`. This demo endpoint has no authentication and must remain local.

### `GET /api/links/{code}/analytics?bucket=day`

Returns `{"code":"...","total_clicks":N,"bucket":"day","series":[{"period":"YYYY-MM-DD","clicks":N}]}`. `bucket` accepts `hour` or `day`.

## Workflow orchestration

### `POST /api/runs`

Request: `{"scenario":"greenfield|brownfield|ambiguous","requirement":"optional override","simulate_failure_stage":"optional stage name"}`. Returns the persisted run snapshot, with status, stages, outputs, lineage, and metrics.

### `GET /api/runs/{run_id}` and `GET /api/runs/{run_id}/events`

Return the current state snapshot or ordered audit events. Stage outputs include structured engineering artifacts and hashes.

### `POST /api/runs/{run_id}/replan`

Request: `{"requirement":"revised requirement"}`. Retains prior stage outputs and any approval in lineage, invalidates the current graph, and computes a new run version.

### `POST /api/runs/{run_id}/approve`

Request: `{"approved":true,"actor":"reviewer","rationale":"review rationale","artifact_hash":"hash from release_readiness output"}`. A decision is accepted only while the run is awaiting approval and only when the supplied artifact hash matches the current release-readiness artifact. Approval or rejection is terminal for that run version.

Errors use `{"error":{"code":"...","message":"..."}}`. Validation errors from FastAPI use its standard `detail` shape.
