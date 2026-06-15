"""In-memory async job store + progress reporting.

A single-user local app doesn't need a database or a task queue: generation runs
in a background thread (so the CPU-bound Kokoro/F5 work stays off the event loop)
and reports progress into a thread-safe ``JobStore``. SSE/poll endpoints read
snapshots from the store.

The orchestrator never touches the store directly — it is handed a
``ProgressReporter`` callable. That keeps the orchestrator testable with a plain
list-appending fake and keeps all locking concerns here.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Protocol

from .models import GenerateResult, JobProgress, JobView


class ProgressReporter(Protocol):
    """Callable the orchestrator uses to report progress. Implemented by the route
    layer (writes to the store) and by tests (records calls)."""

    def __call__(
        self, *, step: str, chunks_done: int, chunks_total: int
    ) -> None: ...


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "queued"  # queued | running | succeeded | failed
    progress: float = 0.0
    step: str = "queued"
    chunks_total: int = 0
    chunks_done: int = 0
    error: str | None = None
    result: GenerateResult | None = None


class JobStore:
    """Thread-safe registry of in-flight and finished jobs (not persisted)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(job_id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            if job.chunks_total > 0:
                job.progress = min(job.chunks_done / job.chunks_total, 1.0)
            if job.status == "succeeded":
                job.progress = 1.0

    def reporter(self, job_id: str) -> ProgressReporter:
        """Return a ProgressReporter bound to ``job_id``."""

        def report(*, step: str, chunks_done: int, chunks_total: int) -> None:
            self.update(
                job_id,
                status="running",
                step=step,
                chunks_done=chunks_done,
                chunks_total=chunks_total,
            )

        return report

    def snapshot(self, job_id: str) -> JobView | None:
        job = self.get(job_id)
        if job is None:
            return None
        return JobView(
            job_id=job.job_id,
            kind=job.kind,  # type: ignore[arg-type]
            progress=JobProgress(
                status=job.status,  # type: ignore[arg-type]
                progress=job.progress,
                step=job.step,
                chunks_total=job.chunks_total,
                chunks_done=job.chunks_done,
                detail=job.error,
            ),
            result=job.result,
        )
