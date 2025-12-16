from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from router.common import normalize_project
from router.schemas import IndexDirectoryRequest, IndexDirectoryResponse, IndexingStatusResponse


router = APIRouter()
logger = logging.getLogger(__name__)


_INDEXING_LOCK = threading.Lock()


def _set_indexing_status(
    request: Request,
    *,
    project: str,
    status: str,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Update in-memory indexing status for a project.

    Args:
        request: FastAPI request whose app state is used as the storage.
        project: Normalized project scope name.
        status: Either "in_progress" or "done".
        started_at: ISO timestamp when the job started.
        finished_at: ISO timestamp when the job finished.
        error: Optional error string if the job failed.
    """

    statuses = getattr(request.app.state, "indexing_statuses", None)
    if not isinstance(statuses, dict):
        request.app.state.indexing_statuses = {}
        statuses = request.app.state.indexing_statuses

    statuses[project] = {
        "project": project,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "error": error,
    }


def _get_indexing_status(request: Request, *, project: str) -> Dict[str, Any]:
    """Read in-memory indexing status for a project.

    Args:
        request: FastAPI request.
        project: Normalized project scope name.

    Returns:
        A dict containing at least: project, status.
    """

    statuses = getattr(request.app.state, "indexing_statuses", None)
    if not isinstance(statuses, dict):
        return {"project": project, "status": "done"}

    value = statuses.get(project)
    if isinstance(value, dict):
        return value
    return {"project": project, "status": "done"}


def _run_index_directory_job(
    request: Request,
    *,
    directory: Path,
    project: str,
    indexed_at: str,
    reindex: bool,
    include_file_summaries: Optional[bool],
) -> None:
    """Run the full indexing pipeline for a project in a background thread.

    Args:
        request: Request whose app state holds the caches and vectorstore.
        directory: Absolute directory to scan.
        project: Normalized project scope name.
        indexed_at: ISO timestamp used for metadata.
        reindex: Whether to delete existing scoped docs first.
        include_file_summaries: Optional flag for indexing per-file summaries.
    """

    started_at = datetime.now(timezone.utc).isoformat()
    _set_indexing_status(request, project=project, status="in_progress", started_at=started_at)

    try:
        # Serialize indexing operations within this process to avoid concurrent writes
        # to shared resources (vectorstore + tree-sitter build artifacts).
        with _INDEXING_LOCK:
            from indexer import scan_java_methods
            from core.parsing.java_parser import JavaParser
            from core.rag.indexing import (
                index_java_file_summaries,
                index_java_methods,
                index_project_overview,
            )
            from core.parsing.tree_sitter_setup import setup_java_language
            from utils.vectorstore import (
                _get_vectorstore,
                _load_method_docs_map,
                delete_scoped_documents,
            )
            from core.rag.retriever import GraphEnrichedRetriever
            from core.project_graph import SqliteProjectGraphStore

            setup_java_language()
            parser = JavaParser()
            config = getattr(request.app.state, "config", None)
            methods = scan_java_methods(
                str(directory),
                parser,
                exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
            )
            if project:
                for m in methods:
                    m.project = project

            if not methods:
                # Keep project_overviews in sync even when nothing was found.
                if not hasattr(request.app.state, "project_overviews"):
                    request.app.state.project_overviews = {}
                request.app.state.project_overviews[project] = {
                    "overview": "",
                    "indexed_path": str(directory),
                    "indexed_at": indexed_at,
                }
                return

            vectorstore = getattr(request.app.state, "vectorstore", None)
            if vectorstore is None:
                vectorstore = _get_vectorstore()
                request.app.state.vectorstore = vectorstore

            if bool(reindex):
                delete_scoped_documents(vectorstore, project=project)

            indexed_map = index_java_methods(methods, vectorstore)

            config = getattr(request.app.state, "config", None)
            effective_include_summaries = (
                bool(include_file_summaries)
                if include_file_summaries is not None
                else bool(getattr(config, "index_file_summaries", False))
            )
            indexed_summaries = 0
            if effective_include_summaries:
                indexed_summaries = len(index_java_file_summaries(methods, vectorstore))

            graph_path = str(
                getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3")
                or "./project_graph.sqlite3"
            )
            graph_store = SqliteProjectGraphStore(sqlite_path=graph_path)
            graph_store.rebuild(project=project, methods=methods)
            graph_overview = graph_store.overview_text(project=project)

            semantic_overview: Optional[str] = None
            file_summaries_by_path: Dict[str, str] = {}
            try:
                from config import AppConfig
                from indexer import iter_java_files
                from utils.chat import create_chat_model
                from core.documentation.feature_extractor import (
                    generate_module_summary,
                    generate_project_overview,
                    summarize_file_semantically,
                )
                from core.documentation.site_generator import write_feature_docs_site

                if not isinstance(config, AppConfig):
                    raise RuntimeError("App config is not available; cannot generate semantic overview")

                llm = create_chat_model(
                    base_url=os.getenv("OPENAI_CHAT_API_BASE"),
                    model=os.getenv("OPENAI_CHAT_MODEL"),
                    temperature=0.0,
                    streaming=False,
                )

                java_files = list(
                    iter_java_files(
                        str(directory),
                        exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
                    )
                )
                by_folder: Dict[Path, List[Path]] = {}
                for fp in java_files:
                    by_folder.setdefault(fp.parent, []).append(fp)

                module_summaries: Dict[str, str] = {}
                for folder in sorted(by_folder.keys(), key=lambda p: str(p)):
                    file_summaries: List[str] = []
                    for fp in sorted(by_folder[folder]):
                        try:
                            code = fp.read_text(encoding="utf-8")
                        except Exception as e:
                            logger.warning("Skipping unreadable file %s: %s", fp, e)
                            code = ""
                        summary = summarize_file_semantically(fp, code, llm)
                        file_summaries.append(summary)
                        file_summaries_by_path[str(fp)] = summary

                    try:
                        key = folder.resolve().relative_to(directory.resolve()).as_posix() or "."
                    except Exception:
                        key = str(folder)

                    module_summaries[key] = generate_module_summary(folder, file_summaries, llm)

                semantic_overview = generate_project_overview(directory, module_summaries, llm).strip()

                docs_base = Path(str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")).expanduser()
                if not docs_base.is_absolute():
                    docs_base = (Path.cwd() / docs_base).resolve()

                # Write docs under a per-project subfolder to avoid overwriting when multiple
                # projects are indexed.
                docs_root = (docs_base / project).resolve()
                docs_root.mkdir(parents=True, exist_ok=True)

                docs_site_root = docs_root / "docs"
                docs_site_root.mkdir(parents=True, exist_ok=True)
                (docs_site_root / "PROJECT_OVERVIEW.md").write_text(
                    semantic_overview + "\n",
                    encoding="utf-8",
                )

                batch_size = int(getattr(config, "docs_feature_batch_size", 10) or 10)
                write_feature_docs_site(
                    output_dir=docs_site_root,
                    project_overview=semantic_overview,
                    file_summaries=file_summaries_by_path,
                    llm=llm,
                    batch_size=batch_size,
                )
            except Exception as e:
                logger.warning(
                    "Semantic project overview generation failed (project=%s): %s", project, e
                )

            overview_to_store = semantic_overview if semantic_overview else (graph_overview or "")
            if overview_to_store.strip():
                index_project_overview(
                    project=project,
                    overview_text=overview_to_store,
                    vectorstore=vectorstore,
                    indexed_path=str(directory),
                    indexed_at=indexed_at,
                )

            persist = getattr(vectorstore, "persist", None)
            if callable(persist):
                persist()

            method_docs_map = _load_method_docs_map(vectorstore, project=project)

            if not hasattr(request.app.state, "method_docs_maps"):
                request.app.state.method_docs_maps = {}
            request.app.state.method_docs_maps[project] = method_docs_map

            if not hasattr(request.app.state, "project_overviews"):
                request.app.state.project_overviews = {}
            request.app.state.project_overviews[project] = {
                "overview": overview_to_store,
                "indexed_path": str(directory),
                "indexed_at": indexed_at,
            }

            if not hasattr(request.app.state, "retrievers"):
                request.app.state.retrievers = {}
            request.app.state.retrievers[project] = GraphEnrichedRetriever(
                vectorstore=vectorstore,
                method_docs_map=method_docs_map,
                k=int(os.getenv("RAG_K", "4")),
                project=project,
            )

            # Keep a small summary in the status store (useful for UI if needed).
            statuses = getattr(request.app.state, "indexing_statuses", None)
            if isinstance(statuses, dict) and isinstance(statuses.get(project), dict):
                statuses[project]["indexed_methods"] = len(indexed_map)
                statuses[project]["indexed_file_summaries"] = int(indexed_summaries)
                statuses[project]["loaded_method_docs"] = len(method_docs_map)
                statuses[project]["indexed_at"] = indexed_at
    except Exception as e:
        finished_at = datetime.now(timezone.utc).isoformat()
        _set_indexing_status(
            request,
            project=project,
            status="done",
            started_at=started_at,
            finished_at=finished_at,
            error=str(e),
        )
        return

    finished_at = datetime.now(timezone.utc).isoformat()
    # Preserve started_at if it was written earlier.
    current = _get_indexing_status(request, project=project)
    _set_indexing_status(
        request,
        project=project,
        status="done",
        started_at=str(current.get("started_at") or started_at),
        finished_at=finished_at,
        error=None,
    )


@router.get("/index-status", response_model=IndexingStatusResponse)
def get_index_status(request: Request, project: str) -> IndexingStatusResponse:
    """Return indexing status for a project scope.

    Args:
        request: FastAPI request.
        project: Project scope name.

    Returns:
        Status information used by the frontend while indexing runs.
    """

    normalized = normalize_project(project)
    value = _get_indexing_status(request, project=normalized)
    return IndexingStatusResponse(
        project=normalized,
        status=str(value.get("status") or "done"),
        started_at=value.get("started_at"),
        finished_at=value.get("finished_at"),
        error=value.get("error"),
    )


@router.post("/index-directory", response_model=IndexDirectoryResponse)
def index_directory(request: Request, req: IndexDirectoryRequest) -> IndexDirectoryResponse:
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
    current = _get_indexing_status(request, project=project)
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
        target=_run_index_directory_job,
        kwargs={
            "request": request,
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
