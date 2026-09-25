import hashlib
import json
import time
import uuid
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.storage import connect, json_dump, now_iso

GRAPHS = {
    "intake": [], "decompose": ["intake"],
    "design": ["decompose"], "security": ["decompose"], "test_plan": ["decompose"],
    "synchronize": ["design", "security", "test_plan"],
    "implementation": ["synchronize"], "validation": ["implementation"],
    "documentation": ["implementation"], "release_readiness": ["validation", "documentation"],
}
SCENARIOS = {
    "greenfield": "Add expiring short links and click analytics.",
    "brownfield": "Add custom aliases to the existing shortener while preserving API compatibility.",
    "ambiguous": "Make links safer and more useful.",
}
RETRY_LIMIT = 2


class WorkflowError(Exception):
    pass


def validate_graph(graph=GRAPHS):
    for stage, dependencies in graph.items():
        unknown = set(dependencies) - set(graph)
        if unknown:
            raise WorkflowError(f"{stage} has unknown dependencies: {sorted(unknown)}")
    visiting, visited = set(), set()

    def visit(stage):
        if stage in visiting:
            raise WorkflowError(f"Workflow dependency cycle includes {stage}")
        if stage in visited:
            return
        visiting.add(stage)
        for dependency in graph[stage]:
            visit(dependency)
        visiting.remove(stage)
        visited.add(stage)

    for stage in graph:
        visit(stage)


validate_graph()


def _event(db, run_id, event_type, detail, stage=None):
    db.execute("INSERT INTO workflow_events(run_id,timestamp,event_type,stage,detail) VALUES(?,?,?,?,?)",
               (run_id, now_iso(), event_type, stage, json_dump(detail)))


def _artifact(kind, title, body, rationale):
    return {"kind": kind, "title": title, "body": body, "rationale": rationale,
            "sha256": hashlib.sha256(body.encode()).hexdigest()}


def _stage_output(stage, requirement, scenario, simulate_failure_stage=None):
    if stage == simulate_failure_stage:
        raise RuntimeError("Injected transient failure for recovery demonstration")
    if stage == "intake":
        ambiguous = scenario == "ambiguous"
        return {"normalized_requirement": requirement,
                "acceptance_criteria": ["Only HTTP(S) URLs are accepted", "Short links resolve to the stored destination",
                                        "Analytics are observable per short code"],
                "ambiguity": (["Define what safer means: abuse prevention, privacy, or destination safety",
                               "Define useful features and analytics retention"] if ambiguous else []),
                "requirement_hash": hashlib.sha256(requirement.encode()).hexdigest()}
    if stage == "decompose":
        tasks = ["Define API and persistence changes", "Implement domain behavior", "Validate compatibility and failure cases",
                 "Document setup, operating limits, and review decisions"]
        return {"tasks": tasks, "risk_tier": "high" if scenario == "brownfield" else "medium",
                "dependencies": {"implementation": ["design", "security", "test_plan"]}}
    if stage == "design":
        output = {"decision": "Keep link and click data behind repository boundaries; persist workflow artifacts and events in SQLite.",
                  "api_changes": ["POST /api/links", "GET /{code}", "GET /api/links/{code}/analytics"],
                  "compatibility": "Additive API behavior; database changes require reviewed migration in production."}
        if scenario == "brownfield":
            output["impacted_components"] = [
                {"module": "app/shortener.py", "impact": "Alias validation, uniqueness, lookup, and link lifecycle behavior."},
                {"module": "app/storage.py", "impact": "Link schema constraints and persistence compatibility."},
                {"module": "app/main.py", "impact": "Create-link contract and API error mapping."},
            ]
            output["data_flow"] = "POST request -> API validation -> shortener service -> SQLite unique code -> response; GET code -> lookup -> destination redirect."
        return output
    if stage == "security":
        return {"controls": ["Allow only absolute HTTP(S) destinations", "Never fetch a submitted URL", 
                             "Reject embedded credentials", "Do not persist client IP or user-agent"],
                "review": "No external side effects are performed by local agents."}
    if stage == "test_plan":
        return {"checks": ["URL and alias validation", "expiry and disabled link behavior", "click aggregation",
                            "API error contracts", "approval and safe-stop transitions"],
                "gate": "Validation artifacts must pass before release readiness."}
    if stage == "synchronize":
        return {"branches_synchronized": ["design", "security", "test_plan"], "ready": True}
    if stage == "implementation":
        return {"artifacts": [
            _artifact("api_contract", "Link API contract", "POST /api/links {url, alias?, expires_at?}; GET /{code} resolves; GET /api/links/{code}/analytics reports click totals and buckets.", "Defines stable service boundaries."),
            _artifact("change_plan", "Implementation change plan", "Add strict URL validation, persist short codes and click events, aggregate analytics, retain expiry state, and return stable typed errors.", "Small domain-focused change with no network fetch of submitted URLs."),
            _artifact("schema", "Storage schema", "links(code PRIMARY KEY, target_url, created_at, expires_at, disabled); clicks(id, code, clicked_at); indexed clicks(code, clicked_at).", "SQLite constraints protect uniqueness and query access."),
        ], "human_review_required": scenario == "brownfield"}
    if stage == "validation":
        return {"result": "passed", "checks": ["requirement coverage mapped", "security controls reviewed", "test plan complete"],
                "limitations": ["Deterministic stage outputs are not proof that arbitrary generated code is correct."]}
    if stage == "documentation":
        return {"artifacts": [_artifact("runbook", "Local run and operations", "Start the API locally, inspect workflow events, and require an operator approval before marking high-impact work ready.", "Keeps human ownership and the local deployment boundary explicit.")]}
    if stage == "release_readiness":
        high_impact = scenario == "brownfield"
        artifact = {"status": "awaiting_approval", "risk_tier": "high" if high_impact else "medium",
                    "checklist": ["API contract reviewed", "validation evidence attached", "rollback or recovery plan documented", "operator approval recorded"],
                    "rollback_plan": "Restore the prior application version; apply a reviewed compensating database migration if data shape changed.",
                    "approval_required": True}
        artifact["approval_hash"] = hashlib.sha256(json_dump(artifact).encode()).hexdigest()
        return artifact
    raise WorkflowError(f"Unknown workflow stage: {stage}")


def _run_state(db, run_id):
    row = db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise WorkflowError("Workflow run not found")
    state = json.loads(row["state"])
    state.update({"id": row["id"], "scenario": row["scenario"], "requirement": row["requirement"],
                  "created_at": row["created_at"], "updated_at": row["updated_at"]})
    return state


def _save(db, run_id, state):
    state["updated_at"] = now_iso()
    db.execute("UPDATE workflow_runs SET state=?,updated_at=? WHERE id=?", (json_dump(state), state["updated_at"], run_id))


def _execute(db, run_id, state, requirement, scenario, simulate_failure_stage=None):
    stage_data = state["stages"]
    for name in GRAPHS:
        stage_data.setdefault(name, {"status": "pending", "attempts": 0, "output": None})
    while True:
        ready = [name for name, dependencies in GRAPHS.items()
                 if stage_data[name]["status"] == "pending"
                 and all(stage_data[d]["status"] == "completed" for d in dependencies)]
        if not ready or state["status"] in ("awaiting_clarification", "safe_stopped"):
            break
        if "intake" in ready and scenario == "ambiguous" and requirement.strip() == SCENARIOS["ambiguous"]:
            current = stage_data["intake"]
            current.update({"status": "blocked", "attempts": 1,
                            "output": _stage_output("intake", requirement, scenario)})
            state["status"] = "awaiting_clarification"
            _event(db, run_id, "safe_stop", {"reason": "Requirement has unresolved consequential ambiguity", "questions": current["output"]["ambiguity"]}, "intake")
            break

        def run_agent(name):
            start = time.monotonic()
            errors = []
            for attempt in range(1, RETRY_LIMIT + 1):
                try:
                    injected = simulate_failure_stage if name == simulate_failure_stage else None
                    result = _stage_output(name, requirement, scenario, injected)
                    return {"output": result, "attempts": attempt,
                            "duration_ms": round((time.monotonic()-start)*1000), "errors": errors}
                except Exception as exc:
                    errors.append(str(exc))
                    if attempt < RETRY_LIMIT:
                        time.sleep(0.1)
            return {"output": {"fallback": "Manual review required", "error": errors[-1]},
                    "attempts": RETRY_LIMIT, "duration_ms": round((time.monotonic()-start)*1000), "errors": errors}

        for name in ready:
            stage_data[name]["status"] = "running"
            _event(db, run_id, "stage_started", {"dependencies": GRAPHS[name], "retry_limit": RETRY_LIMIT}, name)
        _save(db, run_id, state)
        with ThreadPoolExecutor(max_workers=len(ready)) as pool:
            outcomes = dict(zip(ready, pool.map(run_agent, ready)))
        for name in ready:
            current, result = stage_data[name], outcomes[name]
            current.update({"attempts": current["attempts"] + result["attempts"],
                            "duration_ms": result["duration_ms"], "output": result["output"]})
            for attempt, error in enumerate(result["errors"], start=1):
                if attempt < RETRY_LIMIT:
                    _event(db, run_id, "retry_scheduled", {"attempt": attempt, "limit": RETRY_LIMIT,
                                                            "backoff_ms": 100, "error": error}, name)
            if result["errors"]:
                current["status"] = "fallback"
                _event(db, run_id, "fallback", current["output"], name)
                state["status"] = "safe_stopped"
            else:
                current["status"] = "completed"
                _event(db, run_id, "stage_completed", {"output_hash": hashlib.sha256(json_dump(result["output"]).encode()).hexdigest(),
                                                         "duration_ms": current["duration_ms"], "attempts": result["attempts"]}, name)
                if name == "release_readiness":
                    _event(db, run_id, "rollback_planned", {"plan": result["output"]["rollback_plan"]}, name)
        _save(db, run_id, state)
        _save(db, run_id, state)
    if state["status"] not in ("awaiting_clarification", "safe_stopped"):
        if stage_data["release_readiness"]["status"] == "completed":
            state["status"] = "awaiting_approval"
        elif stage_data["release_readiness"]["status"] == "pending":
            state["status"] = "running"
    _save(db, run_id, state)
    return state


def create_run(scenario, requirement=None, simulate_failure_stage=None):
    if scenario not in SCENARIOS:
        raise WorkflowError("scenario must be greenfield, brownfield, or ambiguous")
    requirement = requirement or SCENARIOS[scenario]
    if not requirement.strip() or len(requirement) > 4000:
        raise WorkflowError("requirement must contain 1-4000 characters")
    run_id = str(uuid.uuid4())
    timestamp = now_iso()
    initial = {"status": "running", "stages": {name: {"status": "pending", "attempts": 0, "output": None}
                                                   for name in GRAPHS},
               "lineage": [], "metrics": {}}
    with connect() as db:
        db.execute("INSERT INTO workflow_runs VALUES(?,?,?,?,?,?)",
                   (run_id, scenario, requirement, json_dump(initial), timestamp, timestamp))
        _event(db, run_id, "run_created", {"scenario": scenario, "requirement_hash": hashlib.sha256(requirement.encode()).hexdigest()})
        state = _execute(db, run_id, initial, requirement, scenario, simulate_failure_stage)
        _metrics(db, run_id, state)
        return _run_state(db, run_id)


def _metrics(db, run_id, state):
    events = db.execute("SELECT timestamp,event_type,stage FROM workflow_events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
    retries = sum(e["event_type"] == "retry_scheduled" for e in events)
    rollbacks = sum(e["event_type"] == "rollback_executed" for e in events)
    rollback_plans = sum(e["event_type"] == "rollback_planned" for e in events)
    started = datetime.fromisoformat(events[0]["timestamp"])
    elapsed = max(0, (datetime.now(timezone.utc)-started).total_seconds()*1000)
    retry_starts, recoveries = {}, []
    for event in events:
        if event["event_type"] == "retry_scheduled":
            retry_starts[event["stage"]] = datetime.fromisoformat(event["timestamp"])
        elif event["event_type"] == "stage_completed" and event["stage"] in retry_starts:
            recoveries.append((datetime.fromisoformat(event["timestamp"])-retry_starts.pop(event["stage"])).total_seconds()*1000)
    all_stages = list(state["stages"].values())
    state["metrics"] = {"success_rate": 1.0 if state["status"] == "completed" else 0.0,
                         "retry_count": retries, "rollback_count": rollbacks,
                         "rollback_plan_count": rollback_plans,
                         "mttr_ms": round(sum(recoveries)/len(recoveries)) if recoveries else None,
                         "end_to_end_latency_ms": round(elapsed),
                         "completed_stages": sum(s["status"] == "completed" for s in all_stages),
                         "total_stages": len(GRAPHS)}
    _save(db, run_id, state)


def get_run(run_id):
    with connect() as db:
        return _run_state(db, run_id)


def approve_run(run_id, approved, actor, rationale, artifact_hash=None):
    if not actor.strip() or not rationale.strip():
        raise WorkflowError("actor and rationale are required")
    with connect() as db:
        state = _run_state(db, run_id)
        if state["status"] != "awaiting_approval":
            raise WorkflowError("Run is not waiting for approval")
        release = state["stages"]["release_readiness"]["output"]
        expected = release["approval_hash"]
        if not artifact_hash or artifact_hash != expected:
            raise WorkflowError("Approval artifact hash does not match current release artifact")
        decision = "approved" if approved else "rejected"
        state["approval"] = {"decision": decision, "actor": actor, "rationale": rationale,
                             "artifact_hash": expected, "timestamp": now_iso()}
        state["status"] = "completed" if approved else "rejected"
        _event(db, run_id, "human_approval" if approved else "human_rejection", state["approval"])
        _save(db, run_id, state)
        _metrics(db, run_id, state)
        return _run_state(db, run_id)


def events_for_run(run_id):
    with connect() as db:
        _run_state(db, run_id)
        rows = db.execute("SELECT seq,timestamp,event_type,stage,detail FROM workflow_events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]


def replan_run(run_id, new_requirement):
    if not new_requirement.strip() or len(new_requirement) > 4000:
        raise WorkflowError("requirement must contain 1-4000 characters")
    with connect() as db:
        state = _run_state(db, run_id)
        old_hash = hashlib.sha256(state["requirement"].encode()).hexdigest()
        stale = ["intake", "decompose", "design", "security", "test_plan", "synchronize",
                 "implementation", "validation", "documentation", "release_readiness"]
        state["lineage"].append({"previous_requirement_hash": old_hash, "changed_at": now_iso(),
                                 "invalidated_stages": stale, "prior_state": state["status"],
                                 "prior_stages": copy.deepcopy(state["stages"]),
                                 "prior_approval": copy.deepcopy(state.get("approval"))})
        for stage in stale:
            previous = state["stages"].get(stage)
            attempts = previous.get("attempts", 0) if previous else 0
            state["stages"][stage] = {"status": "pending", "attempts": 0, "prior_attempts": attempts, "output": None}
        state["status"] = "running"
        state.pop("approval", None)
        scenario = state["scenario"]
        db.execute("UPDATE workflow_runs SET requirement=? WHERE id=?", (new_requirement, run_id))
        _event(db, run_id, "replan", {"old_requirement_hash": old_hash,
                                      "new_requirement_hash": hashlib.sha256(new_requirement.encode()).hexdigest(),
                                      "invalidated_stages": stale})
        _execute(db, run_id, state, new_requirement, scenario)
        _metrics(db, run_id, state)
        return _run_state(db, run_id)
