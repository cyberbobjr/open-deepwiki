from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import HTTPException, Request


def normalize_project(project: str) -> str:
    """Normalize and validate a project scope string.

    Args:
        project: Project scope name.

    Returns:
        Normalized project name.

    Raises:
        HTTPException: If the project name is empty.
    """

    p = str(project or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="project is required")
    return p


def get_scoped_retriever(request: Request, *, project: str):
    """Return (and cache) a scoped retriever + scoped method_docs_map.

    Args:
        request: FastAPI request.
        project: Project scope name.

    Returns:
        A GraphEnrichedRetriever instance.
    """

    from utils.vectorstore import _load_method_docs_map
    from core.rag.retriever import GraphEnrichedRetriever

    if not hasattr(request.app.state, "retrievers"):
        request.app.state.retrievers = {}
    if not hasattr(request.app.state, "method_docs_maps"):
        request.app.state.method_docs_maps = {}

    retrievers: Dict[str, Any] = request.app.state.retrievers
    maps: Dict[str, Dict[str, Any]] = request.app.state.method_docs_maps

    vectorstore = getattr(request.app.state, "vectorstore")

    if project not in maps:
        maps[project] = _load_method_docs_map(vectorstore, project=project)

    if project not in retrievers:
        retrievers[project] = GraphEnrichedRetriever(
            vectorstore=vectorstore,
            method_docs_map=maps[project],
            k=int(os.getenv("RAG_K", "4")),
            project=project,
        )
    else:
        retrievers[project].vectorstore = vectorstore
        retrievers[project].method_docs_map = maps[project]
        retrievers[project].project = project

    return retrievers[project]
