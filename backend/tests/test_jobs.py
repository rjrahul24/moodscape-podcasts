from app.core.jobs import JobStore
from app.core.models import GenerateResult


def test_create_and_get():
    store = JobStore()
    job = store.create("podcast")
    assert store.get(job.job_id) is job
    assert store.snapshot(job.job_id).progress.status == "queued"


def test_progress_math_from_chunks():
    store = JobStore()
    job = store.create("podcast")
    store.update(job.job_id, status="running", chunks_done=2, chunks_total=8, step="x")
    view = store.snapshot(job.job_id)
    assert view.progress.progress == 0.25
    assert view.progress.chunks_done == 2


def test_succeeded_forces_full_progress_and_carries_result():
    store = JobStore()
    job = store.create("sleep_story")
    result = GenerateResult(job_id=job.job_id, duration_ms=1000, segments=[], files=[])
    store.update(job.job_id, status="succeeded", result=result)
    view = store.snapshot(job.job_id)
    assert view.progress.progress == 1.0
    assert view.progress.status == "succeeded"
    assert view.result.duration_ms == 1000


def test_failed_captures_error_detail():
    store = JobStore()
    job = store.create("podcast")
    store.update(job.job_id, status="failed", error="boom")
    view = store.snapshot(job.job_id)
    assert view.progress.status == "failed"
    assert view.progress.detail == "boom"


def test_reporter_updates_store():
    store = JobStore()
    job = store.create("podcast")
    report = store.reporter(job.job_id)
    report(step="Synthesizing 1/3", chunks_done=1, chunks_total=3)
    view = store.snapshot(job.job_id)
    assert view.progress.step == "Synthesizing 1/3"
    assert view.progress.status == "running"


def test_snapshot_missing_returns_none():
    assert JobStore().snapshot("nope") is None
