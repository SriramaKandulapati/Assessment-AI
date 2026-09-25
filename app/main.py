from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.config import BASE_URL
from app.orchestration import (WorkflowError, approve_run, create_run, events_for_run,
                               get_run, replan_run)
from app.shortener import ShortenerError, create_link, disable_link, link_analytics, resolve_link
from app.storage import init_db


@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="Agentic URL Shortener", version="0.1.0", lifespan=lifespan,
              description="URL shortening APIs and a governed, stateful engineering workflow prototype.")


class LinkCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    alias: str | None = None
    expires_at: str | None = None


class WorkflowCreate(BaseModel):
    scenario: str = Field(pattern="^(greenfield|brownfield|ambiguous)$")
    requirement: str | None = Field(default=None, max_length=4000)
    simulate_failure_stage: str | None = None


class Approval(BaseModel):
    approved: bool
    actor: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=2000)
    artifact_hash: str | None = None


class Replan(BaseModel):
    requirement: str = Field(min_length=1, max_length=4000)


@app.exception_handler(ShortenerError)
async def shortener_error(_request: Request, exc: ShortenerError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(WorkflowError)
async def workflow_error(_request: Request, exc: WorkflowError):
    status = 404 if "not found" in str(exc).lower() else 409
    return JSONResponse(status_code=status, content={"error": {"code": "workflow_error", "message": str(exc)}})


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentic-shortener"}


@app.post("/api/links", status_code=201)
def create_short_link(body: LinkCreate):
    row = create_link(body.url, body.alias, body.expires_at)
    return {"code": row["code"], "short_url": f"{BASE_URL}/{row['code']}", "url": row["target_url"],
            "created_at": row["created_at"], "expires_at": row["expires_at"]}


@app.get("/api/links/{code}/analytics")
def get_analytics(code: str, bucket: str = "day"):
    return link_analytics(code, bucket)


@app.post("/api/links/{code}/disable")
def disable_short_link(code: str):
    return disable_link(code)


@app.post("/api/runs", status_code=201)
def start_workflow(body: WorkflowCreate):
    return create_run(body.scenario, body.requirement, body.simulate_failure_stage)


@app.get("/api/runs/{run_id}")
def inspect_workflow(run_id: str):
    return get_run(run_id)


@app.get("/api/runs/{run_id}/events")
def workflow_events(run_id: str):
    return {"run_id": run_id, "events": events_for_run(run_id)}


@app.post("/api/runs/{run_id}/approve")
def workflow_approval(run_id: str, body: Approval):
    return approve_run(run_id, body.approved, body.actor, body.rationale, body.artifact_hash)


@app.post("/api/runs/{run_id}/replan")
def workflow_replan(run_id: str, body: Replan):
    return replan_run(run_id, body.requirement)


@app.get("/{code}")
def resolve_short_link(code: str):
    return RedirectResponse(resolve_link(code), status_code=307)
