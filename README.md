# Agentic URL Shortener

A local URL shortener paired with a deterministic, stateful orchestration prototype. The service demonstrates how engineering work can move from a natural-language requirement through decomposition, parallel reviews, implementation artifacts, validation, documentation, and a human release gate. Local agents emit structured proposals; the orchestrator enforces dependencies and approvals.

## Quick start

Requires Python 3.11 or later.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m app.cli serve
```

The API listens on `http://127.0.0.1:8000`. Interactive OpenAPI documentation is at `/docs`.
Set `DATABASE_PATH`, `BASE_URL`, `HOST`, and `PORT` to override local defaults (see `.env.example`; the app does not load `.env` automatically).

Docker alternative: `docker compose up --build`.

## URL shortener API

Create a link:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/links `
  -ContentType 'application/json' `
  -Body '{"url":"https://example.com/products","alias":"products"}'
```

Resolve by opening `http://127.0.0.1:8000/products` (HTTP 307 redirect; records a click). Optional `expires_at` must be a future timezone-aware ISO 8601 timestamp. Query analytics with `GET /api/links/products/analytics?bucket=day` (`hour` is also supported). Disable a code with `POST /api/links/products/disable`.

## Run the three orchestration scenarios

```powershell
python -m app.cli demo greenfield
python -m app.cli demo brownfield
python -m app.cli demo ambiguous
```

Greenfield and brownfield runs execute independent design, security, and test-plan stages after decomposition, synchronize them, and stop at a persisted human approval gate. The ambiguous scenario asks clarification questions and safe-stops before implementation. Inject a repeated failure to see bounded retry, fallback, and safe stop:

```powershell
python -m app.cli demo greenfield --fail-stage implementation
```

The API provides the same workflow operations: `POST /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/events`, `POST /api/runs/{id}/replan`, and `POST /api/runs/{id}/approve`. Copy `approval_hash` from the current `release_readiness` stage output and send it with the decision, for example `{"approved":true,"actor":"reviewer","rationale":"Reviewed the release evidence","artifact_hash":"<approval_hash>"}`. Rejections are also recorded and terminal. The decision is rejected if the hash does not match the current release artifact.

## Architecture

See [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md), [docs/threat-model.md](docs/threat-model.md), and [docs/demo-script.md](docs/demo-script.md). The stage graph and deterministic agent outputs live in `app/orchestration.py`; shortener rules and persistence live in `app/shortener.py` and `app/storage.py`; HTTP contracts are in `app/main.py`.

The graph has explicit dependencies and a synchronization gate. Each run persists stage status, attempts, typed output, approval decisions, and append-only events in SQLite. Re-planning invalidates dependent stages and retains previous requirement hashes and prior attempt counts. The CLI/API expose success state, retry/rollback counts, stage counts, and elapsed time.

## Validation

Validation scenarios are described under `scenarios/`. Install development dependencies and run the included automated suite:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

Coverage includes domain edge cases, API/database flows, approval/hash gates, graph scheduling, retries, safe stops, and re-planning lineage.

## Boundaries and limitations

- Deterministic local agents demonstrate orchestration semantics, not autonomous code modification or general language understanding.
- SQLite and the in-process workflow runner suit a single-user demo, not multi-instance production deployment.
- Click data is aggregate-oriented but has no retention job, deduplication key, abuse controls, or rate limiting.
- No custom aliases are authenticated or reserved; the demo should not be exposed publicly.
- The service never fetches the submitted destination, reducing SSRF risk. It does not classify malicious destinations.
- Approval is a demo identity string, not enterprise identity or a cryptographic signature. Release execution is deliberately outside the system.
- Rollback is a documented compensating-action plan. No automatic destructive rollback is attempted.
