from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.models.user import User
from core.security import get_current_maintainer, get_current_user
from router.common import normalize_project
from router.schemas import (IndexDirectoryRequest, IndexDirectoryResponse,
                            IndexingStatusResponse)
from services.indexing import get_indexing_status, run_index_directory_job

router = APIRouter()
logger = logging.getLogger(__name__)






@router.get("/index-status", response_model=IndexingStatusResponse)
def get_index_status(
    request: Request, 
    project: str,
    current_user: User = Depends(get_current_user)
) -> IndexingStatusResponse:
    """Return indexing status for a project scope.

    Args:
        request: FastAPI request.
        project: Project scope name.

    Returns:
        Status information used by the frontend while indexing runs.
    """

    normalized = normalize_project(project)
    value = get_indexing_status(request.app.state, project=normalized)
    return IndexingStatusResponse(
        project=normalized,
        status=str(value.get("status") or "done"),
        started_at=value.get("started_at"),
        finished_at=value.get("finished_at"),
        error=value.get("error"),
        total_files=value.get("total_files"),
        processed_files=value.get("processed_files"),
        remaining_files=value.get("remaining_files"),
        current_file=value.get("current_file"),
    )


@router.post("/index-directory", response_model=IndexDirectoryResponse)
def index_directory(
    request: Request, 
    req: IndexDirectoryRequest,
    current_user: User = Depends(get_current_maintainer)
) -> IndexDirectoryResponse:
    """Index a directory of Java files into a project scope."""

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; indexing requires embeddings.",
        )

    directory = Path(req.path).expanduser()
    if not directory.is_absolute():
        directory = (Path.cwd() / directory).resolve()

    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {directory}")

    project = normalize_project(req.project)
    indexed_at = datetime.now(timezone.utc).isoformat()

    # If a job is already running for this project, do not start another.
    current = get_indexing_status(request.app.state, project=project)
    if str(current.get("status") or "done") == "in_progress":
        return IndexDirectoryResponse(
            path=str(directory),
            project=project,
            indexed_methods=0,
            indexed_file_summaries=0,
            loaded_method_docs=len(
                (getattr(request.app.state, "method_docs_maps", {}) or {}).get(project, {}) or {}
            ),
            indexed_at=indexed_at,
            status="in_progress",
        )

    # Kick off the work in a background daemon thread and return immediately.
    worker = threading.Thread(
        target=run_index_directory_job,
        kwargs={
            "app_state": request.app.state,
            "directory": directory,
            "project": project,
            "indexed_at": indexed_at,
            "reindex": bool(req.reindex),
            "include_file_summaries": req.include_file_summaries,
        },
        daemon=True,
        name=f"index-directory::{project}",
    )
    worker.start()

    return IndexDirectoryResponse(
        path=str(directory),
        project=project,
        indexed_methods=0,
        indexed_file_summaries=0,
        loaded_method_docs=len(
            (getattr(request.app.state, "method_docs_maps", {}) or {}).get(project, {}) or {}
        ),
        indexed_at=indexed_at,
        status="in_progress",
    )
