def test_link_and_workflow_api_end_to_end(client):
    created = client.post("/api/links", json={"url": "https://example.com/path", "alias": "api-link"})
    assert created.status_code == 201
    resolved = client.get("/api-link", follow_redirects=False)
    assert resolved.status_code == 307
    assert resolved.headers["location"] == "https://example.com/path"
    analytics = client.get("/api/links/api-link/analytics")
    assert analytics.json()["total_clicks"] == 1
    disabled = client.post("/api/links/api-link/disable")
    assert disabled.json()["disabled"] is True
    assert client.get("/api-link").status_code == 410

    run = client.post("/api/runs", json={"scenario": "greenfield"}).json()
    assert run["status"] == "awaiting_approval"
    release_hash = run["stages"]["release_readiness"]["output"]["approval_hash"]
    approved = client.post(f"/api/runs/{run['id']}/approve", json={
        "approved": True, "actor": "reviewer", "rationale": "Reviewed demo evidence",
        "artifact_hash": release_hash,
    })
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
