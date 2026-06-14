"""Synchronous episode generation + file download."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import SettingsDep
from app.core import engine
from app.core.errors import (
    ProviderError,
    ProviderNotFoundError,
    ScriptParseError,
    VoiceAssignmentError,
)
from app.core.models import GenerateRequest, GenerateResult
from app.storage import files

router = APIRouter()


@router.post("/generate", response_model=GenerateResult)
def generate(request: GenerateRequest, settings: SettingsDep) -> GenerateResult:
    try:
        return engine.generate(request, settings)
    except (ScriptParseError, VoiceAssignmentError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/download/{job_id}/{filename}")
def download(job_id: str, filename: str, settings: SettingsDep) -> FileResponse:
    path = files.resolve_download(settings.output_dir, job_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, filename=filename)
