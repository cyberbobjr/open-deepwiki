from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from core.access_control import validate_project_access
from core.database import get_session
from core.models.user import User
from core.security import get_current_user
from router.common import get_scoped_retriever, normalize_project
from router.schemas import QueryRequest, QueryResult

router = APIRouter()


@router.post("/query", response_model=List[QueryResult])
def query(
    request: Request, 
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> List[QueryResult]:
    """Vector similarity search within a project scope."""
    
    validate_project_access(session, current_user, req.project)

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot query embeddings-backed vector search.",
        )

    project = normalize_project(req.project)
    retriever = get_scoped_retriever(request, project=project)
    retriever.k = req.k

    docs = retriever.get_relevant_documents(req.query)
    results: List[QueryResult] = []
    for doc in docs:
        meta = doc.metadata or {}
        results.append(
            QueryResult(
                id=meta.get("id"),
                signature=meta.get("signature"),
                type=meta.get("type"),
                calls=meta.get("calls"),
                has_docstring=meta.get("has_docstring"),
                file_path=meta.get("file_path"),
                start_line=meta.get("start_line"),
                end_line=meta.get("end_line"),
                is_dependency=bool(meta.get("is_dependency", False)),
                called_from=meta.get("called_from"),
                page_content=doc.page_content,
            )
        )

    return results
