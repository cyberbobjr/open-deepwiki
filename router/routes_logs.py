from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

from core.documentation.postimplementation_log import get_log_dir_from_env, safe_log_filename
from router.schemas import (
    PostImplementationLogInfo,
    PostImplementationLogListResponse,
    PostImplementationLogReadResponse,
)


router = APIRouter()


@router.get("/postimplementation-logs", response_model=PostImplementationLogListResponse)
def list_postimplementation_logs() -> PostImplementationLogListResponse:
    """List postimplementation logs."""

    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    if not log_dir.exists():
        return PostImplementationLogListResponse(log_dir=str(log_dir), logs=[])
    if not log_dir.is_dir():
        raise HTTPException(
            status_code=500,
            detail=f"POSTIMPLEMENTATION_LOG_DIR is not a directory: {log_dir}",
        )

    logs: List[PostImplementationLogInfo] = []
    for entry in sorted(log_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not entry.is_file():
            continue
        if not entry.name.startswith("postimplementation_") or not entry.name.endswith(".log"):
            continue
        try:
            size = entry.stat().st_size
            modified_at = entry.stat().st_mtime
        except Exception:
            size = 0
            modified_at = 0.0
        logs.append(
            PostImplementationLogInfo(
                filename=entry.name,
                size_bytes=size,
                modified_at=float(modified_at),
            )
        )

    return PostImplementationLogListResponse(log_dir=str(log_dir), logs=logs)


@router.get(
    "/postimplementation-logs/{filename}",
    response_model=PostImplementationLogReadResponse,
)
def read_postimplementation_log(filename: str) -> PostImplementationLogReadResponse:
    """Read a specific postimplementation log file by name."""

    safe = safe_log_filename(filename)
    if safe is None:
        raise HTTPException(status_code=400, detail="Invalid log filename")

    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    path = (log_dir / safe).resolve()

    if log_dir not in path.parents and path != log_dir:
        raise HTTPException(status_code=400, detail="Invalid log filename")

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")

    return PostImplementationLogReadResponse(filename=safe, content=content)
