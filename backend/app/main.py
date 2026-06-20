"""FastAPI application factory."""

from __future__ import annotations

import logging
import shutil
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ambient, generate, health, jobs, series, voices
from app.config import get_settings
from app.core.jobs import JobStore
from app.providers.bootstrap import bootstrap_providers

logger = logging.getLogger("moodscape")


def create_app() -> FastAPI:
    settings = get_settings()
    bootstrap_providers(settings)

    if shutil.which("ffmpeg") is None:
        logger.warning(
            "ffmpeg not found on PATH. Audio stitching/export will fail. "
            "Install it (e.g. `brew install ffmpeg`)."
        )

    app = FastAPI(title="Moodscape Podcasts", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared async-job state. A single-slot executor serializes jobs so two heavy
    # local models never load at once (OOM guard) and keeps generation off the
    # event loop.
    app.state.job_store = JobStore()
    app.state.job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")

    app.include_router(health.router, prefix="/api")
    app.include_router(voices.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(ambient.router, prefix="/api")
    app.include_router(series.router, prefix="/api")
    return app


app = create_app()
