from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# External libraries
from langchain_openai import ChatOpenAI

from config import AppConfig
# Documentation / RAG imports
from core.documentation.feature_extractor import (generate_module_summary,
                                                  generate_project_overview)
from core.documentation.site_generator import write_feature_docs_site
from core.parsing.generic_parser import GenericAppParser
from core.parsing.java_parser import JavaParser
from core.parsing.tree_sitter_setup import setup_java_language
from core.project_graph import SqliteProjectGraphStore
from core.rag.indexing import (index_generated_markdown_docs,
                               index_java_file_summaries, index_java_methods,
                               index_project_overview)
from core.rag.retriever import GraphEnrichedRetriever
# Internal imports
from indexer import scan_java_methods, scan_resource_files
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


def run_index_directory_job(
    app_state: Any,
    *,
    directory: Path,
    project: str,
    indexed_at: str,
    reindex: bool,
    include_file_summaries: Optional[bool] = None,

) -> None:
    """Run the full indexing pipeline for a project in a background thread.

    Args:
        app_state: App state holds the caches and vectorstore.
        directory: Absolute directory to scan.
        project: Normalized project scope name.
        indexed_at: ISO timestamp used for metadata.
        reindex: Whether to delete existing scoped docs first.

        reindex: Whether to delete existing scoped docs first.
        include_file_summaries: Optional flag for indexing per-file summaries.
    """

    started_at = datetime.now(timezone.utc).isoformat()
    set_indexing_status(app_state, project=project, status="in_progress", started_at=started_at)

    try:
        # Serialize indexing operations within this process to avoid concurrent writes
        # to shared resources (vectorstore + tree-sitter build artifacts).
        with INDEXING_LOCK:
            setup_java_language()
            parser = JavaParser()
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
                )

            methods = scan_java_methods(
                str(directory),
                parser,
                exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
                progress_callback=_progress,
            )
            if project:
                for m in methods:
                    m.project = project

            if not methods:
                # Keep project_overviews in sync even when nothing was found.
                if not hasattr(app_state, "project_overviews"):
                    app_state.project_overviews = {}
                app_state.project_overviews[project] = {
                    "overview": "",
                    "indexed_path": str(directory),
                    "indexed_at": indexed_at,
                }
                return

            vectorstore = getattr(app_state, "vectorstore", None)
            if vectorstore is None:
                vectorstore = _get_vectorstore()
                app_state.vectorstore = vectorstore

            if bool(reindex):
                delete_scoped_documents(vectorstore, project=project)

            indexed_map = index_java_methods(methods, vectorstore)



            graph_path = str(
                getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3")
                or "./project_graph.sqlite3"
            )
            graph_store = SqliteProjectGraphStore(sqlite_path=graph_path)
            graph_store.rebuild(project=project, methods=methods)
            graph_overview = graph_store.overview_text(project=project)


            overview_to_store = graph_overview or ""

            # --- Heuristic File Summaries (Optional) ---
            indexed_summaries = 0
            if include_file_summaries is None:
                include_file_summaries = bool(getattr(config, "index_file_summaries", False))

            file_summaries_by_path: Dict[str, str] = {}
            if include_file_summaries:
                # Call the function with correct arguments (methods list)
                summaries_map = index_java_file_summaries(
                    methods=methods,
                    vectorstore=vectorstore,
                )
                indexed_summaries = len(summaries_map)
                
                # Convert Dict[(project, path), Document] to Dict[path, content]
                for (proj, fpath), doc in summaries_map.items():
                    file_summaries_by_path[str(fpath)] = doc.page_content

            # --- Generic Resource Indexing (YAML, JSON, etc.) ---
            indexed_resources = 0
            if getattr(config, "index_resources", True):
                resource_parser = GenericAppParser()
                # Get configured extensions and chunk size
                extensions = getattr(config, "resource_extensions", []) or [
                    ".yaml", ".yml", ".json", ".xml", ".properties", ".txt", ".md"
                ]
                chunk_size = int(getattr(config, "resource_chunk_size", 1000) or 1000)
                
                resource_docs = scan_resource_files(
                    codebase_dir=str(directory),
                    extensions=extensions,
                    parser=resource_parser,
                    chunk_size=chunk_size,
                    progress_callback=None,  # Or hook into existing progress?
                )
                
                if resource_docs:
                    # Enrich metadata with project context
                    for doc in resource_docs:
                        doc.metadata["project"] = project
                        doc.metadata["type"] = "resource"
                        doc.metadata["indexed_at"] = indexed_at
                        # Ensure language is set (use extension without dot)
                        ext = doc.metadata.get("extension", "")
                        doc.metadata["language"] = ext.lstrip(".") if ext else "text"

                    # Add to vectorstore
                    # Note: we might need to batch this if very large, but Chroma/LangChain handle batching usually.
                    vectorstore.add_documents(resource_docs)
                    indexed_resources = len(resource_docs)
                    
            # --- Semantic Documentation Generation (Features, Modules, Overview) ---
            # This step uses an LLM to "understand" the codebase and generate higher-level docs.
            semantic_overview: Optional[str] = None
            try:
                llm = None
                if os.getenv("OPENAI_API_KEY"):
                    llm = ChatOpenAI(
                        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
                        temperature=0,
                        api_key=os.getenv("OPENAI_API_KEY"),
                    )

                # Generate features -> modules -> project overview
                # We need file-level summaries to do this effectively.
                # If we didn't index them above, we might generate them transiently here (not implemented yet),
                # or repurpose the ones we just indexed.
                # simpler approach: we rely on file_summaries_by_path populated above.
                # If that's empty (because include_file_summaries=False), we might skip or do a lightweight scan.
                # For now, we reuse the scanned methods map if needed, but better to have summaries.

                # If we have no summaries, let's at least generate them in memory if possible?
                # The original code passed `file_summaries` (heuristic) to `generate_feature_summary`.
                # If `file_summaries_by_path` is empty, this step might be weak.
                # But we proceed.

                module_summaries = {}
                # Identify modules (folders with src/main/java or just top-level folders)
                # For simplicity, we treat subdirectories of 'directory' as modules if they contain java files.
                # This logic mimics the original behavior.

                # Actually, relying on `file_summaries_by_path` keys (files) to infer structure.
                # We group files by parent directory.
                files_by_dir: Dict[str, List[str]] = {}
                for fpath, summary in file_summaries_by_path.items():
                    parent = str(Path(fpath).parent)
                    if parent not in files_by_dir:
                        files_by_dir[parent] = []
                    files_by_dir[parent].append(summary)

                # 1. Feature/Module summaries
                # (This is a simplification of the full logic - we just pass summaries to the generator)
                # But if we don't have file summaries, we can't do much.
                # So we only do this if we have summaries.
                if file_summaries_by_path and llm:
                    feature_summaries = {}
                    for folder, summaries in files_by_dir.items():
                        # We call it "feature" or "module".
                        # Let's assume each folder is a feature for now.
                        feat_sum = generate_module_summary(Path(folder), summaries, llm)
                        feature_summaries[folder] = feat_sum

                    # 2. Project Overview from feature summaries
                    semantic_overview = generate_project_overview(
                        str(directory), feature_summaries, llm
                    ).strip()

                    # 3. Generate Static Docs Site
                    docs_base = Path(
                        str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")
                    ).expanduser()
                    if not docs_base.is_absolute():
                        docs_base = (Path.cwd() / docs_base).resolve()

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

                    # Index generated markdown docs
                    index_generated_markdown_docs(
                        project=project,
                        docs_root=docs_site_root,
                        vectorstore=vectorstore,
                    )

            except Exception as e:
                logger.warning(
                    "Semantic project overview generation failed (project=%s): %s", project, e
                )

            # Update the stored overview if semantic generation succeeded, else fallback to graph
            if semantic_overview:
                overview_to_store = semantic_overview
                # Re-index with the newer semantic text
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

            if not hasattr(app_state, "method_docs_maps"):
                app_state.method_docs_maps = {}
            app_state.method_docs_maps[project] = method_docs_map

            if not hasattr(app_state, "project_overviews"):
                app_state.project_overviews = {}
            app_state.project_overviews[project] = {
                "overview": overview_to_store,
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

            # Keep a small summary in the status store (useful for UI if needed).
            statuses = getattr(app_state, "indexing_statuses", None)
            if isinstance(statuses, dict) and isinstance(statuses.get(project), dict):
                statuses[project]["indexed_methods"] = len(indexed_map)
                statuses[project]["indexed_file_summaries"] = int(indexed_summaries)
                statuses[project]["indexed_resources"] = int(indexed_resources)

                statuses[project]["loaded_method_docs"] = len(method_docs_map)
                statuses[project]["indexed_at"] = indexed_at
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
    # Preserve started_at if it was written earlier.
    current = get_indexing_status(app_state, project=project)
    set_indexing_status(
        app_state,
        project=project,
        status="done",
        started_at=str(current.get("started_at") or started_at),
        finished_at=finished_at,
        error=None,
    )
