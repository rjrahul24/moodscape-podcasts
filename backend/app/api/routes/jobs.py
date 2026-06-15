"""Async generation jobs: create, poll, and stream progress.

``POST /api/jobs`` returns a job id immediately and runs the (CPU-bound)
generation in a single-slot thread pool, off the event loop. Clients watch
progress via SSE (``GET /api/jobs/{id}/events``) or polling
(``GET /api/jobs/{id}``). Long jobs no longer hold the request open or time out.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import SettingsDep
from app.config import Settings
from app.core import orchestrator
from app.core.jobs import JobStore
from app.core.models import JobCreated, JobRequest, JobView

logger = logging.getLogger("moodscape")

router = APIRouter()


def _run_job(store: JobStore, job_id: str, request, settings: Settings) -> None:
    """Worker body (runs in the job executor thread)."""
    store.update(job_id, status="running", step="Starting")
    try:
        result = orchestrator.run(
            request, settings, store.reporter(job_id), job_id=job_id
        )
        store.update(job_id, status="succeeded", step="Done", result=result)
    except Exception as exc:  # noqa: BLE001 - capture any failure into the job
        logger.exception("Job %s failed", job_id)
        store.update(job_id, status="failed", step="Failed", error=str(exc))


@router.post("/jobs", response_model=JobCreated, status_code=202)
def create_job(
    request: JobRequest, http_request: Request, settings: SettingsDep
) -> JobCreated:
    store: JobStore = http_request.app.state.job_store
    executor = http_request.app.state.job_executor
    job = store.create(request.kind)
    executor.submit(_run_job, store, job.job_id, request, settings)
    return JobCreated(job_id=job.job_id)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, http_request: Request) -> JobView:
    view = http_request.app.state.job_store.snapshot(job_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return view


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, http_request: Request) -> EventSourceResponse:
    store: JobStore = http_request.app.state.job_store
    if store.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_gen():
        last: str | None = None
        while True:
            if await http_request.is_disconnected():
                break
            view = store.snapshot(job_id)
            if view is None:
                break
            payload = view.progress.model_dump_json()
            if payload != last:
                yield {"event": "progress", "data": payload}
                last = payload
            if view.progress.status in ("succeeded", "failed"):
                yield {"event": "done", "data": view.model_dump_json()}
                break
            await asyncio.sleep(0.3)

    return EventSourceResponse(
        event_gen(),
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
