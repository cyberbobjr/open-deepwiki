from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, HTTPException, Request

from router.common import get_scoped_retriever, normalize_project
from router.schemas import QueryRequest, QueryResult


router = APIRouter()


@router.post("/query", response_model=List[QueryResult])
def query(request: Request, req: QueryRequest) -> List[QueryResult]:
    """Vector similarity search within a project scope."""

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
                has_javadoc=meta.get("has_javadoc"),
                file_path=meta.get("file_path"),
                start_line=meta.get("start_line"),
                end_line=meta.get("end_line"),
                is_dependency=bool(meta.get("is_dependency", False)),
                called_from=meta.get("called_from"),
                page_content=doc.page_content,
            )
        )

    return results
