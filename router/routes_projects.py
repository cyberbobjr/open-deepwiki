from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from router.common import normalize_project
from router.schemas import (DeleteProjectRequest, DeleteProjectResponse,
                            ProjectDocsIndexResponse, ProjectDocsTocResponse,
                            ProjectInfo, ProjectOverviewRequest,
                            ProjectOverviewResponse)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/projects", response_model=List[str])
def list_indexed_projects(request: Request) -> List[str]:
    """List distinct indexed project scopes.

    Returns only explicit, non-empty project names (docs without a project scope are omitted).
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    vectorstore = getattr(request.app.state, "vectorstore", None)
    if vectorstore is None:
        return []

    collection = getattr(vectorstore, "_collection", None)
    if collection is None:
        return []

    try:
        payload = collection.get(include=["metadatas"])
    except TypeError:
        payload = collection.get()

    metadatas = (payload or {}).get("metadatas") or []
    projects = set()
    for meta in metadatas:
        if not isinstance(meta, dict):
            continue
        value = meta.get("project")
        if value is None:
            continue
        name = str(value).strip()
        if name:
            projects.add(name)

    return sorted(projects)


@router.get("/projects/details", response_model=List[ProjectInfo])
def list_indexed_projects_with_details(request: Request) -> List[ProjectInfo]:
    """List projects with last indexing metadata (path + timestamp).

    Notes:
        This uses in-memory `app.state.project_overviews` when available, otherwise
        falls back to Chroma metadata for the `project_overview` document.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    vectorstore = getattr(request.app.state, "vectorstore", None)
    collection = getattr(vectorstore, "_collection", None) if vectorstore is not None else None

    project_overviews = getattr(request.app.state, "project_overviews", None) or {}

    # Derive project list from the vectorstore metadata (same behavior as /projects).
    projects: List[str] = []
    if collection is not None:
        try:
            payload = collection.get(include=["metadatas"])
        except TypeError:
            payload = collection.get()

        metadatas = (payload or {}).get("metadatas") or []
        uniq = set()
        for meta in metadatas:
            if not isinstance(meta, dict):
                continue
            value = meta.get("project")
            if value is None:
                continue
            name = str(value).strip()
            if name:
                uniq.add(name)
        projects = sorted(uniq)

    out: List[ProjectInfo] = []
    for p in projects:
        indexed_path = None
        indexed_at = None

        entry = project_overviews.get(p)
        if isinstance(entry, dict):
            indexed_path = entry.get("indexed_path")
            indexed_at = entry.get("indexed_at")

        # Fallback to Chroma overview doc metadata.
        if (not indexed_path or not indexed_at) and collection is not None:
            scoped_id = f"{p}::project::overview" if p else "project::overview"
            try:
                payload = collection.get(ids=[scoped_id], include=["metadatas"])
                metas = (payload or {}).get("metadatas") or []
                if metas and isinstance(metas[0], dict):
                    indexed_path = indexed_path or metas[0].get("indexed_path")
                    indexed_at = indexed_at or metas[0].get("indexed_at")
            except Exception:
                pass

        out.append(
            ProjectInfo(
                project=p,
                indexed_path=str(indexed_path).strip() if isinstance(indexed_path, str) and indexed_path.strip() else None,
                indexed_at=str(indexed_at).strip() if isinstance(indexed_at, str) and indexed_at.strip() else None,
            )
        )

    return out


@router.post("/project-overview", response_model=ProjectOverviewResponse)
def get_project_overview(request: Request, req: ProjectOverviewRequest) -> ProjectOverviewResponse:
    """Return the most recently generated project overview for a scope.

    Args:
        request: FastAPI request.
        req: Request payload containing the project scope.

    Returns:
        Latest stored overview for the normalized project.

    Raises:
        HTTPException: If no overview exists for the requested project.

    Notes:
        Overviews are stored in-memory in `app.state.project_overviews` and refreshed during indexing.
    """

    normalized_project = normalize_project(req.project)
    project_overviews = getattr(request.app.state, "project_overviews", None) or {}
    entry = project_overviews.get(normalized_project)

    overview_text: str = ""
    indexed_path = None
    indexed_at = None

    if isinstance(entry, str):
        overview_text = entry
    elif isinstance(entry, dict):
        overview_text = str(entry.get("overview") or "")
        indexed_path = entry.get("indexed_path")
        indexed_at = entry.get("indexed_at")

    # If not cached in memory (e.g., app restart), fall back to vectorstore.
    if not overview_text.strip():
        vectorstore = getattr(request.app.state, "vectorstore", None)
        collection = getattr(vectorstore, "_collection", None) if vectorstore is not None else None
        scoped_id = f"{normalized_project}::project::overview" if normalized_project else "project::overview"

        if collection is not None:
            try:
                payload = collection.get(ids=[scoped_id], include=["documents", "metadatas"])
                docs = (payload or {}).get("documents") or []
                metas = (payload or {}).get("metadatas") or []
                if docs and isinstance(docs[0], str):
                    overview_text = docs[0]
                if metas and isinstance(metas[0], dict):
                    indexed_path = metas[0].get("indexed_path")
                    indexed_at = metas[0].get("indexed_at")
            except Exception:
                pass

    if not overview_text.strip():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No project overview available for project={normalized_project!r}. Run /index-directory first."
            ),
        )

    return ProjectOverviewResponse(
        project=normalized_project,
        overview=overview_text.strip(),
        indexed_path=str(indexed_path).strip() if isinstance(indexed_path, str) and indexed_path.strip() else None,
        indexed_at=str(indexed_at).strip() if isinstance(indexed_at, str) and indexed_at.strip() else None,
    )



@router.post("/project-docs-toc", response_model=ProjectDocsTocResponse)
def get_project_docs_toc(request: Request, req: ProjectOverviewRequest) -> ProjectDocsTocResponse:
    """Return the generated `toc.json` for a project.

    Args:
        request: FastAPI request.
        req: Request payload containing the project scope.

    Returns:
        The JSON content of `<docs_output_dir>/<project>/toc.json`.

    Raises:
        HTTPException: If the toc.json is missing for the requested project.
    """

    normalized_project = normalize_project(req.project)

    config = getattr(request.app.state, "config", None)
    docs_base = Path(str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")).expanduser()
    if not docs_base.is_absolute():
        docs_base = (Path.cwd() / docs_base).resolve()

    docs_root = (docs_base / normalized_project / "docs").resolve()
    # toc.json is inside docs/ because site_generator receives the docs/ folder as output_dir
    toc_path = docs_root / "toc.json"

    if not toc_path.exists() or not toc_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No generated docs TOC found for project={normalized_project!r}. "
                "Run /index-directory first."
            ),
        )

    import json
    try:
        content = json.loads(toc_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
         raise HTTPException(
            status_code=500,
            detail=f"Failed to parse toc.json for project={normalized_project!r}.",
        )

    updated_at: str | None = None
    try:
        mtime = toc_path.stat().st_mtime
        updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except Exception:
        updated_at = None

    return ProjectDocsTocResponse(
        project=normalized_project,
        toc=content,
        updated_at=updated_at,
    )


@router.get("/projects/{project}/docs/{doc_path:path}")
def read_project_doc_file(request: Request, project: str, doc_path: str) -> PlainTextResponse:
    """Serve a generated markdown file from the per-project OUTPUT docs directory.

    This is intended for the UI to resolve links like `features/<slug>.md` when
    rendering `docs/index.md`.

    Args:
        request: FastAPI request.
        project: Project scope name.
        doc_path: Path under the project's `docs/` folder.

    Returns:
        A plaintext response containing the markdown file.

    Raises:
        HTTPException: If the file does not exist or the path is unsafe.
    """

    normalized_project = normalize_project(project)
    requested = str(doc_path or "").lstrip("/")

    if not requested or requested in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid doc path")
    if "\\" in requested:
        raise HTTPException(status_code=400, detail="Invalid doc path")

    config = getattr(request.app.state, "config", None)
    docs_base = Path(str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")).expanduser()
    if not docs_base.is_absolute():
        docs_base = (Path.cwd() / docs_base).resolve()

    docs_root = (docs_base / normalized_project / "docs").resolve()
    target = (docs_root / requested).resolve()

    try:
        target.relative_to(docs_root)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid doc path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Doc not found")

    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=415, detail="Only .md files are supported")

    content = target.read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


def _delete_project_scope(request: Request, *, normalized_project: str) -> DeleteProjectResponse:
    """Delete all persisted data for a project scope.

    This removes:
    - Chroma documents tagged with metadata.project
    - Project graph rows for that project
    - Persisted chat/checkpointer sessions for that project namespace
    - Generated docs output directory under config.docs_output_dir/<project>

    Args:
        request: FastAPI request.
        normalized_project: Normalized project scope name.

    Returns:
        A response describing what was deleted.
    """

    deleted_vectorstore_docs = False
    deleted_graph = False
    deleted_sessions = 0
    deleted_output_dir = False

    # Delete scoped vectorstore documents.
    vectorstore = getattr(request.app.state, "vectorstore", None)
    if vectorstore is not None:
        try:
            from utils.vectorstore import delete_scoped_documents

            delete_scoped_documents(vectorstore, project=normalized_project)
            deleted_vectorstore_docs = True
        except Exception as e:
            logger.warning("Failed to delete scoped vectorstore docs (project=%s): %s", normalized_project, e)

    # Clear in-memory caches.
    for attr in ("retrievers", "method_docs_maps", "project_overviews"):
        cache = getattr(request.app.state, attr, None)
        if isinstance(cache, dict):
            cache.pop(normalized_project, None)

    # Delete graph data by rebuilding the graph with an empty method set.
    try:
        config = getattr(request.app.state, "config", None)
        graph_path = str(
            getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3")
            or "./project_graph.sqlite3"
        )
        from core.project_graph import SqliteProjectGraphStore

        store = SqliteProjectGraphStore(sqlite_path=graph_path)
        store.rebuild(project=normalized_project, methods=[])
        deleted_graph = True
    except Exception as e:
        logger.warning("Failed to delete project graph data (project=%s): %s", normalized_project, e)

    # Delete all persisted conversation sessions for this project scope.
    try:
        from utils.sqlite_checkpointer import SqliteCheckpointSaver

        config = getattr(request.app.state, "config", None)
        cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
        if cp_backend == "sqlite":
            cp_path = str(
                getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3")
                or "./checkpoints.sqlite3"
            )
            cp_path_key = str(Path(cp_path).expanduser().resolve())

            if not hasattr(request.app.state, "checkpointers"):
                request.app.state.checkpointers = {}
            checkpointers = request.app.state.checkpointers
            if cp_path_key not in checkpointers:
                checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
            checkpointer = checkpointers[cp_path_key]

            session_ids = list(checkpointer.list_threads_namespace(checkpoint_ns=normalized_project))
            for sid in session_ids:
                checkpointer.delete_thread_namespace(thread_id=sid, checkpoint_ns=normalized_project)
            deleted_sessions = len(session_ids)
        else:
            logger.warning(
                "Unsupported checkpointer_backend for project deletion: %s (project=%s)",
                cp_backend,
                normalized_project,
            )
    except Exception as e:
        logger.warning("Failed to delete sessions (project=%s): %s", normalized_project, e)

    # Delete generated docs from the configured OUTPUT dir.
    try:
        config = getattr(request.app.state, "config", None)
        base = Path(str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")).expanduser()
        base_resolved = base.resolve() if base.is_absolute() else (Path.cwd() / base).resolve()
        target = (base_resolved / normalized_project).resolve()

        # Safety: ensure we only delete inside the configured base directory.
        base_prefix = str(base_resolved) + os.sep
        if str(target).startswith(base_prefix) and target.exists() and target.is_dir():
            shutil.rmtree(target)
            deleted_output_dir = True
    except Exception as e:
        logger.warning("Failed to delete output docs directory (project=%s): %s", normalized_project, e)

    return DeleteProjectResponse(
        project=normalized_project,
        deleted=True,
        deleted_vectorstore_docs=deleted_vectorstore_docs,
        deleted_graph=deleted_graph,
        deleted_sessions=int(deleted_sessions),
        deleted_output_dir=deleted_output_dir,
    )


@router.delete("/projects", response_model=DeleteProjectResponse)
def delete_project(request: Request, req: DeleteProjectRequest) -> DeleteProjectResponse:
    """Delete a project scope.

    The project name MUST be provided in the request body.

    Args:
        request: FastAPI request.
        req: Request body containing the project scope.

    Returns:
        A response describing what was deleted.

    Raises:
        HTTPException: If startup failed.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    normalized_project = normalize_project(req.project)
    return _delete_project_scope(request, normalized_project=normalized_project)


@router.delete("/projects/{project}", response_model=DeleteProjectResponse, deprecated=True)
def delete_project_legacy(request: Request, project: str) -> DeleteProjectResponse:
    """(Deprecated) Delete a project scope using a path parameter.

    Prefer calling DELETE /projects with a JSON body: {"project": "..."}.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    normalized_project = normalize_project(project)
    return _delete_project_scope(request, normalized_project=normalized_project)
