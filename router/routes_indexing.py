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
                            IndexingStatusResponse,
                            RegenerateDocumentationRequest,
                            RegenerateDocumentationResponse)
from services.indexing import (get_indexing_status, run_index_directory_job,
                               run_regenerate_documentation_job)

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
        step=value.get("step"),
        details=value.get("details"),
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


@router.post("/regenerate-documentation", response_model=RegenerateDocumentationResponse)
def regenerate_documentation(
    request: Request,
    req: RegenerateDocumentationRequest,
    current_user: User = Depends(get_current_maintainer)
) -> RegenerateDocumentationResponse:
    """Regenerate docs for an existing project scope."""
    
    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
        
    project = normalize_project(req.project)
    # Check if project exists in app state or vectorstore
    overviews = getattr(request.app.state, "project_overviews", {})
    project_data = overviews.get(project)
    
    directory = None
    if project_data:
        directory = Path(project_data.get("indexed_path", ""))
    
    # If not in memory, try fetching from Chroma
    if not directory or not directory.exists():
        vectorstore = getattr(request.app.state, "vectorstore", None)
        collection = getattr(vectorstore, "_collection", None) if vectorstore is not None else None
        
        if collection:
            scoped_id = f"{project}::project::overview" if project else "project::overview"
            try:
                payload = collection.get(ids=[scoped_id], include=["metadatas"])
                metas = (payload or {}).get("metadatas") or []
                if metas and isinstance(metas[0], dict):
                    path_str = metas[0].get("indexed_path")
                    if path_str:
                        directory = Path(path_str)
            except Exception as e:
                logger.warning("Failed to recover project path from Chroma: %s", e)

    if not directory or not directory.exists():
         raise HTTPException(status_code=404, detail=f"Project '{project}' path not found. Index it first.")

    # Check if job already running
    current = get_indexing_status(request.app.state, project=project)
    if str(current.get("status") or "done") == "in_progress":
         raise HTTPException(status_code=409, detail=f"Indexing/Regeneration in progress for '{project}'.")
         
    # Launch background job
    worker = threading.Thread(
        target=run_regenerate_documentation_job,
        kwargs={
            "app_state": request.app.state,
            "directory": directory,
            "project": project,
        },
        daemon=True,
        name=f"regenerate-docs::{project}",
    )
    worker.start()

    return RegenerateDocumentationResponse(
        project=project,
        status="in_progress"
    )
