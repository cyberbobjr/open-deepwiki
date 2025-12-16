from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.documentation.postimplementation_log import get_log_dir_from_env
from router.schemas import (
    GenerateJavadocJobResponse,
    GenerateJavadocRequest,
    JavadocJobInfo,
    JavadocSessionLogResponse,
)


router = APIRouter()


@router.post("/generate-javadoc", response_model=GenerateJavadocJobResponse, status_code=202)
def generate_javadoc(request: Request, req: GenerateJavadocRequest) -> GenerateJavadocJobResponse:
    """Start a JavaDoc generation job."""

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot generate JavaDoc.",
        )

    directory = Path(req.path).expanduser()
    if not directory.is_absolute():
        directory = (Path.cwd() / directory).resolve()

    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {directory}")

    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    config = getattr(request.app.state, "config", None)
    min_lines = getattr(config, "javadoc_min_meaningful_lines", 3)

    try:
        job = JAVADOC_JOB_MANAGER.start(
            str(directory), min_meaningful_lines=int(min_lines)
        )
        return GenerateJavadocJobResponse(
            job_id=job.job_id,
            root_dir=job.root_dir,
            status=job.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start JavaDoc generation: {e}")


@router.get("/generate-javadoc/jobs", response_model=List[JavadocJobInfo])
def list_generate_javadoc_jobs() -> List[JavadocJobInfo]:
    """List active/recent JavaDoc generation jobs."""

    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    jobs = JAVADOC_JOB_MANAGER.list()
    return [
        JavadocJobInfo(
            job_id=j.job_id,
            root_dir=j.root_dir,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            stop_requested=bool(j.stop_requested),
            log_file=getattr(j, "log_file", None),
            summary=j.summary,
            error=j.error,
        )
        for j in jobs
    ]


@router.post("/generate-javadoc/jobs/{job_id}/stop", response_model=JavadocJobInfo)
def stop_generate_javadoc_job(job_id: str) -> JavadocJobInfo:
    """Request stopping a JavaDoc job."""

    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    try:
        j = JAVADOC_JOB_MANAGER.stop(job_id)
        return JavadocJobInfo(
            job_id=j.job_id,
            root_dir=j.root_dir,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            stop_requested=bool(j.stop_requested),
            log_file=getattr(j, "log_file", None),
            summary=j.summary,
            error=j.error,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get(
    "/generate-javadoc/sessions/{session_id}/log",
    response_model=JavadocSessionLogResponse,
)
def read_javadoc_session_log(session_id: str) -> JavadocSessionLogResponse:
    """Read the postimplementation log for a JavaDoc generation session."""

    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    if not log_dir.exists() or not log_dir.is_dir():
        raise HTTPException(status_code=404, detail="Log directory not found")

    log_path: Optional[Path] = None
    try:
        from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

        jobs = JAVADOC_JOB_MANAGER.list()
        for j in jobs:
            if j.job_id == session_id and getattr(j, "log_file", None):
                log_path = Path(str(j.log_file)).expanduser().resolve()
                break
    except Exception:
        log_path = None

    if log_path is None:
        suffix = f"_{session_id}.log"
        for entry in log_dir.iterdir():
            if (
                entry.is_file()
                and entry.name.startswith("postimplementation_")
                and entry.name.endswith(suffix)
            ):
                log_path = entry.resolve()
                break

    if log_path is None:
        raise HTTPException(status_code=404, detail="Session log not found")

    if log_dir not in log_path.parents and log_path != log_dir:
        raise HTTPException(status_code=400, detail="Invalid session log path")

    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="Session log not found")

    try:
        content = log_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session log: {e}")

    return JavadocSessionLogResponse(
        session_id=session_id,
        filename=log_path.name,
        content=content,
    )
