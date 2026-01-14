from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Documentation / RAG imports
from core.documentation.pipeline import run_documentation_pipeline
from core.parsing.models import CodeBlock
from core.parsing.tree_sitter_setup import setup_languages
from core.project_graph import SqliteProjectGraphStore
from core.rag.indexing import index_code_blocks, index_file_summaries
from core.rag.retriever import GraphEnrichedRetriever
# Internal imports
from core.scanning.scanner import scan_codebase
from utils.vectorstore import (_get_vectorstore, _load_method_docs_map,
                               delete_scoped_documents)

logger = logging.getLogger(__name__)

INDEXING_LOCK = threading.Lock()


def set_indexing_status(
    app_state: Any,
    *,
    project: str,
    status: str,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    error: Optional[str] = None,
    total_files: Optional[int] = None,
    processed_files: Optional[int] = None,
    remaining_files: Optional[int] = None,

    current_file: Optional[str] = None,
    step: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Update in-memory indexing status for a project.

    Args:
        app_state: Application state object (e.g. request.app.state).
        project: Normalized project scope name.
        status: Either "in_progress" or "done".
        started_at: ISO timestamp when the job started.
        finished_at: ISO timestamp when the job finished.
        error: Optional error string if the job failed.
        total_files: Optional total number of Java files that will be scanned.
        processed_files: Optional number of files already processed.
        remaining_files: Optional number of files remaining.
        current_file: Optional file path currently being processed (best-effort).
        step: Specific step name (e.g. "scanning", "graph").
        details: Human readable details.
    """

    statuses = getattr(app_state, "indexing_statuses", None)
    if not isinstance(statuses, dict):
        app_state.indexing_statuses = {}
        statuses = app_state.indexing_statuses

    existing = statuses.get(project)
    entry: Dict[str, Any] = existing if isinstance(existing, dict) else {}
    entry["project"] = project
    entry["status"] = status
    if started_at is not None:
        entry["started_at"] = started_at
    if finished_at is not None:
        entry["finished_at"] = finished_at

    # Allow clearing errors by explicitly setting error=None.
    entry["error"] = error

    if total_files is not None:
        entry["total_files"] = int(total_files)
    if processed_files is not None:
        entry["processed_files"] = int(processed_files)
    if remaining_files is not None:
        entry["remaining_files"] = int(remaining_files)
    if current_file is not None:
        entry["current_file"] = current_file
    if step is not None:
        entry["step"] = step
    if details is not None:
        entry["details"] = details

    statuses[project] = entry


def get_indexing_status(app_state: Any, *, project: str) -> Dict[str, Any]:
    """Read in-memory indexing status for a project.

    Args:
        app_state: Application state object (e.g. request.app.state).
        project: Normalized project scope name.

    Returns:
        A dict containing at least: project, status.
    """

    statuses = getattr(app_state, "indexing_statuses", None)
    if not isinstance(statuses, dict):
        return {"project": project, "status": "done"}

    value = statuses.get(project)
    if isinstance(value, dict):
        return value
    return {"project": project, "status": "done"}


def _scan_and_index_codebase(
    directory: Path,
    project: str,
    config: Any,
    app_state: Any,
    reindex: bool,
    progress_callback: Any,
) -> Tuple[List[CodeBlock], Any]:
    """Scan codebase and index code blocks."""
    blocks = scan_codebase(
        str(directory),
        exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
        progress_callback=progress_callback,
    )
    if project:
        for b in blocks:
            b.project = project

    if not blocks:
        return [], None

    vectorstore = getattr(app_state, "vectorstore", None)
    if vectorstore is None:
        vectorstore = _get_vectorstore()
        app_state.vectorstore = vectorstore

    if bool(reindex):
        delete_scoped_documents(vectorstore, project=project)

    index_code_blocks(blocks, vectorstore)
    return blocks, vectorstore


def _build_project_graph(project: str, config: Any, blocks: List[CodeBlock]) -> str:
    """Rebuild project graph and return overview text."""
    graph_path = str(
        getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3")
        or "./project_graph.sqlite3"
    )
    graph_store = SqliteProjectGraphStore(sqlite_path=graph_path)
    graph_store.rebuild(project=project, methods=blocks)
    return graph_store.overview_text(project=project) or ""


def _index_heuristic_summaries(
    blocks: List[CodeBlock],
    vectorstore: Any,
    config: Any,
    include_file_summaries: Optional[bool],
) -> Tuple[int, Dict[str, str]]:
    """Index heuristic file summaries if enabled."""
    if include_file_summaries is None:
        include_file_summaries = bool(getattr(config, "index_file_summaries", False))

    if not include_file_summaries:
        return 0, {}

    summaries_map = index_file_summaries(methods=blocks, vectorstore=vectorstore)
    
    # Convert Dict[(project, path), Document] to Dict[path, content]
    file_summaries_by_path = {}
    for (_, fpath), doc in summaries_map.items():
        file_summaries_by_path[str(fpath)] = doc.page_content
        
    return len(summaries_map), file_summaries_by_path





def _finalize_app_state(
    app_state: Any,
    project: str,
    directory: Path,
    indexed_at: str,
    vectorstore: Any,
    overview_text: str,
    metrics: Dict[str, int],
) -> None:
    """Update application state with final indexing results."""
    # Chroma V2 handles persistence automatically


    method_docs_map = _load_method_docs_map(vectorstore, project=project)

    if not hasattr(app_state, "method_docs_maps"):
        app_state.method_docs_maps = {}
    app_state.method_docs_maps[project] = method_docs_map

    if not hasattr(app_state, "project_overviews"):
        app_state.project_overviews = {}
    app_state.project_overviews[project] = {
        "overview": overview_text,
        "indexed_path": str(directory),
        "indexed_at": indexed_at,
    }

    if not hasattr(app_state, "retrievers"):
        app_state.retrievers = {}
    app_state.retrievers[project] = GraphEnrichedRetriever(
        vectorstore=vectorstore,
        method_docs_map=method_docs_map,
        k=int(os.getenv("RAG_K", "4")),
        project=project,
    )

    statuses = getattr(app_state, "indexing_statuses", None)
    if isinstance(statuses, dict) and isinstance(statuses.get(project), dict):
        status = statuses[project]
        status["indexed_methods"] = metrics.get("indexed_methods", 0)
        status["indexed_file_summaries"] = metrics.get("indexed_summaries", 0)
        status["indexed_resources"] = 0  # Disabled for now
        status["loaded_method_docs"] = len(method_docs_map)
        status["indexed_at"] = indexed_at



def run_regenerate_documentation_job(
    app_state: Any,
    *,
    directory: Path,
    project: str,
) -> None:
    """Run only the documentation pipeline for a project in a background thread."""
    started_at = datetime.now(timezone.utc).isoformat()
    set_indexing_status(
        app_state, 
        project=project, 
        status="in_progress", 
        started_at=started_at,
        step="starting",
        details="Initializing documentation regeneration..."
    )

    try:
        with INDEXING_LOCK:
            config = getattr(app_state, "config", None)
            
            if os.getenv("OPENAI_API_KEY"):
                set_indexing_status(app_state, project=project, status="in_progress", step="semantic", details="Regenerating semantic documentation...")
                docs_base = Path(
                    str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")
                ).expanduser()
                if not docs_base.is_absolute():
                    docs_base = (Path.cwd() / docs_base).resolve()
                
                output_path = docs_base / project / "docs" / "PROJECT_OVERVIEW.md"
                site_output_dir = docs_base / project / "docs"

                try:
                    def _pipeline_progress(step: str, details: str) -> None:
                        set_indexing_status(
                            app_state,
                            project=project,
                            status="in_progress",
                            step=step,
                            details=details
                        )
                   
                    run_documentation_pipeline(
                        root_dir=directory,
                        config=config,
                        output_path=output_path,
                        site_output_dir=site_output_dir,
                        index_into_chroma=True, # Update index with new overview
                        max_files=None,
                        precomputed_file_summaries=None, # Re-generate fresh
                        progress_callback=_pipeline_progress,
                        indexed_at=started_at,
                        indexed_path=str(directory),
                        project_name=project,
                    )
                    final_overview = output_path.read_text(encoding="utf-8")
                    
                    # Update App State
                    if not hasattr(app_state, "project_overviews"):
                        app_state.project_overviews = {}
                    
                    # Keep existing metadata if possible
                    existing = app_state.project_overviews.get(project, {})
                    app_state.project_overviews[project] = {
                        "overview": final_overview,
                        "indexed_path": str(directory),
                        "indexed_at": existing.get("indexed_at") or started_at, # Keep original indexed_at or update? Maybe update is better to indicate freshness of overview
                    }
                    
                    # Update retriever if needed? Retriever uses vectorstore. 
                    # If run_documentation_pipeline indexed into chroma, then vectorstore is updated.
                    # So next retrieval will pick up new overview.
                    
                except Exception as e:
                    logger.warning("Regeneration failed: %s", e)
                    raise e
            else:
                 raise RuntimeError("OPENAI_API_KEY not set")

    except Exception as e:
        finished_at = datetime.now(timezone.utc).isoformat()
        set_indexing_status(
            app_state,
            project=project,
            status="done",
            started_at=started_at,
            finished_at=finished_at,
            error=str(e),
        )
        return

    finished_at = datetime.now(timezone.utc).isoformat()
    current = get_indexing_status(app_state, project=project)
    set_indexing_status(
        app_state,
        project=project,
        status="done",
        started_at=str(current.get("started_at") or started_at),
        finished_at=finished_at,
        error=None,
    )


def run_index_directory_job(
    app_state: Any,
    *,
    directory: Path,
    project: str,
    indexed_at: str,
    reindex: bool,
    include_file_summaries: Optional[bool] = None,
) -> None:
    """Run the full indexing pipeline for a project in a background thread."""
    started_at = datetime.now(timezone.utc).isoformat()
    set_indexing_status(
        app_state, 
        project=project, 
        status="in_progress", 
        started_at=started_at,
        step="starting",
        details="Initializing indexing job..."
    )

    try:
        with INDEXING_LOCK:
            setup_languages()
            config = getattr(app_state, "config", None)

            def _progress(processed: int, total: int, current_file: Optional[str]) -> None:
                remaining = max(int(total) - int(processed), 0)
                set_indexing_status(
                    app_state,
                    project=project,
                    status="in_progress",
                    total_files=int(total),
                    processed_files=int(processed),
                    remaining_files=int(remaining),
                    current_file=current_file,
                    step="scanning",
                    details=f"Scanning files: {processed}/{total}"
                )

            # 1. Scan and Index Code
            set_indexing_status(app_state, project=project, status="in_progress", step="scanning", details="Scanning codebase...")
            blocks, vectorstore = _scan_and_index_codebase(
                directory, project, config, app_state, reindex, _progress
            )
            
            if not blocks:
                if not hasattr(app_state, "project_overviews"):
                    app_state.project_overviews = {}
                app_state.project_overviews[project] = {
                    "overview": "",
                    "indexed_path": str(directory),
                    "indexed_at": indexed_at,
                }
                return

            # 2. Build Project Graph
            set_indexing_status(app_state, project=project, status="in_progress", step="graph", details="Building dependency graph...")
            graph_overview = _build_project_graph(project, config, blocks)
            
            # 3. Index Heuristic Summaries
            set_indexing_status(app_state, project=project, status="in_progress", step="heuristics", details="Indexing heuristic summaries...")
            indexed_summaries, file_summaries_by_path = _index_heuristic_summaries(
                blocks, vectorstore, config, include_file_summaries
            )

            # 4. Generate Semantic Documentation (LLM) using Pipeline
            if os.getenv("OPENAI_API_KEY"):
                set_indexing_status(app_state, project=project, status="in_progress", step="semantic", details="Generating semantic documentation...")
                docs_base = Path(
                    str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")
                ).expanduser()
                if not docs_base.is_absolute():
                    docs_base = (Path.cwd() / docs_base).resolve()
                
                output_path = docs_base / project / "docs" / "PROJECT_OVERVIEW.md"
                site_output_dir = docs_base / project / "docs"

                try:
                    def _pipeline_progress(step: str, details: str) -> None:
                        set_indexing_status(
                            app_state,
                            project=project,
                            status="in_progress",
                            step=step,
                            details=details
                        )

                    run_documentation_pipeline(
                        root_dir=directory,
                        config=config,
                        output_path=output_path,
                        site_output_dir=site_output_dir,
                        index_into_chroma=True, # Allow pipeline to index the overview
                        max_files=None,
                        precomputed_file_summaries=file_summaries_by_path,
                        progress_callback=_pipeline_progress,
                        indexed_at=indexed_at,
                        indexed_path=str(directory),
                        project_name=project,
                    )
                    final_overview = output_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error("Semantic generation failed via pipeline: %s", e, exc_info=True)
                    raise e
            else:
                final_overview = ""

            if not final_overview:
                final_overview = graph_overview

            # 5. Finalize State
            set_indexing_status(app_state, project=project, status="in_progress", step="finalizing", details="Finalizing index...")
            metrics = {
                "indexed_methods": len(blocks),
                "indexed_summaries": indexed_summaries,
            }
            _finalize_app_state(
                app_state,
                project,
                directory,
                indexed_at,
                vectorstore,
                final_overview,
                metrics
            )

    except Exception as e:
        finished_at = datetime.now(timezone.utc).isoformat()
        set_indexing_status(
            app_state,
            project=project,
            status="done",
            started_at=started_at,
            finished_at=finished_at,
            error=str(e),
        )
        return

    finished_at = datetime.now(timezone.utc).isoformat()
    current = get_indexing_status(app_state, project=project)
    set_indexing_status(
        app_state,
        project=project,
        status="done",
        started_at=str(current.get("started_at") or started_at),
        finished_at=finished_at,
        error=None,
    )
