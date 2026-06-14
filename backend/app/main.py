"""FastAPI application factory."""

from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import generate, health, voices
from app.config import get_settings
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

    app = FastAPI(title="Moodscape Podcasts", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(voices.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    return app


app = create_app()
