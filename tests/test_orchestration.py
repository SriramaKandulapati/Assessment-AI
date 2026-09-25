from app.orchestration import approve_run, create_run, replan_run


def test_parallel_branches_join_and_approval_gate(client):
    run = create_run("greenfield")
    assert run["status"] == "awaiting_approval"
    for stage in ("design", "security", "test_plan"):
        assert run["stages"][stage]["status"] == "completed"
    assert run["stages"]["synchronize"]["output"]["ready"] is True
    approval_hash = run["stages"]["release_readiness"]["output"]["approval_hash"]
    approved = approve_run(run["id"], True, "reviewer", "Evidence reviewed", approval_hash)
    assert approved["status"] == "completed"
    assert approved["metrics"]["success_rate"] == 1.0


def test_ambiguity_and_bounded_failure_stop(client):
    unclear = create_run("ambiguous")
    assert unclear["status"] == "awaiting_clarification"
    assert unclear["stages"]["implementation"]["status"] == "pending"
    failed = create_run("greenfield", simulate_failure_stage="implementation")
    assert failed["status"] == "safe_stopped"
    assert failed["stages"]["implementation"]["attempts"] == 2


def test_replan_records_lineage_and_requires_new_approval(client):
    run = create_run("greenfield")
    revised = replan_run(run["id"], "Add expiring short links, click analytics, and a 90-day retention policy.")
    assert revised["status"] == "awaiting_approval"
    assert len(revised["lineage"]) == 1
    assert revised["lineage"][0]["prior_stages"]["implementation"]["status"] == "completed"
    assert revised["stages"]["intake"]["status"] == "completed"
    assert "approval" not in revised
