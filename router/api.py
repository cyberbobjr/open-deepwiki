from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from core.documentation.postimplementation_log import get_log_dir_from_env, safe_log_filename


router = APIRouter()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)
    project: str = Field(
        ...,
        min_length=1,
        description="Project scope name (required). Retrieval is restricted to documents indexed with the same project.",
    )


class QueryResult(BaseModel):
    id: Optional[str] = None
    signature: Optional[str] = None
    type: Optional[str] = None
    calls: Any = None
    has_javadoc: Optional[bool] = None
    is_dependency: bool = False
    called_from: Optional[str] = None
    page_content: str


class IndexDirectoryRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Chemin du répertoire à indexer (scan récursif des .java).")
    project: str = Field(
        ...,
        min_length=1,
        description="Project scope name (required) attached to indexed docs.",
    )
    reindex: bool = Field(
        default=False,
        description="If true, deletes existing docs in this scope before indexing.",
    )
    include_file_summaries: Optional[bool] = Field(
        default=None,
        description="If true, indexes one summary document per Java file (heuristic, no LLM). Defaults to config.index_file_summaries.",
    )


class IndexDirectoryResponse(BaseModel):
    path: str
    project: str
    indexed_methods: int
    indexed_file_summaries: int = 0
    loaded_method_docs: int


class GenerateJavadocRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Chemin du répertoire à scanner (récursif).")


class GenerateJavadocResponse(BaseModel):
    root_dir: str
    files_scanned: int
    files_modified: int
    members_documented: int
    log_file: str


class GenerateJavadocJobResponse(BaseModel):
    job_id: str
    root_dir: str
    status: str


class JavadocJobInfo(BaseModel):
    job_id: str
    root_dir: str
    status: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    stop_requested: bool
    log_file: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class JavadocSessionLogResponse(BaseModel):
    session_id: str
    filename: str
    content: str


class PostImplementationLogInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_at: float


class PostImplementationLogListResponse(BaseModel):
    log_dir: str
    logs: List[PostImplementationLogInfo]


class PostImplementationLogReadResponse(BaseModel):
    filename: str
    content: str


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


class ProjectQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)


@router.post("/projects/{project}/query", response_model=List[QueryResult])
def query_in_project(project: str, request: Request, req: ProjectQueryRequest) -> List[QueryResult]:
    """Query within a project provided in the URL path."""

    return query(request, QueryRequest(query=req.query, k=req.k, project=project))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)
    project: str = Field(
        ...,
        min_length=1,
        description="Project scope name (required). Retrieval is restricted to documents indexed with the same project.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Conversation session id. If omitted, a new session id is created and returned.",
    )


class AskResponse(BaseModel):
    session_id: str
    project: str
    answer: str
    context: List[QueryResult]


def _normalize_project(project: str) -> str:
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


def _get_scoped_retriever(request: Request, *, project: str):
    """Return (and cache) a scoped retriever + scoped method_docs_map."""

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


class ProjectAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)
    session_id: Optional[str] = Field(
        default=None,
        description="Conversation session id. If omitted, a new session id is created and returned.",
    )


@router.post("/projects/{project}/ask", response_model=AskResponse)
def ask_in_project(project: str, request: Request, req: ProjectAskRequest) -> AskResponse:
    """Ask within a project provided in the URL path."""

    return ask(
        request,
        AskRequest(
            question=req.question,
            k=req.k,
            project=project,
            session_id=req.session_id,
        ),
    )


class ProjectIndexDirectoryRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Chemin du répertoire à indexer (scan récursif des .java).")
    reindex: bool = Field(
        default=False,
        description="If true, deletes existing docs in this scope before indexing.",
    )
    include_file_summaries: Optional[bool] = Field(
        default=None,
        description="If true, indexes one summary document per Java file (heuristic, no LLM). Defaults to config.index_file_summaries.",
    )


@router.post("/projects/{project}/index-directory", response_model=IndexDirectoryResponse)
def index_directory_in_project(
    project: str, request: Request, req: ProjectIndexDirectoryRequest
) -> IndexDirectoryResponse:
    """Index a directory into a project provided in the URL path."""

    return index_directory(
        request,
        IndexDirectoryRequest(
            path=req.path,
            project=project,
            reindex=req.reindex,
            include_file_summaries=req.include_file_summaries,
        ),
    )




@router.get("/health")
def health(request: Request) -> Dict[str, Any]:
    config = getattr(request.app.state, "config", None)
    method_maps = getattr(request.app.state, "method_docs_maps", None) or {}
    loaded_scopes = list(method_maps.keys()) if isinstance(method_maps, dict) else []
    loaded_total = 0
    if isinstance(method_maps, dict):
        for _, m in method_maps.items():
            try:
                loaded_total += len(m or {})
            except Exception:
                pass
    return {
        "status": "ok",
        "config_path": getattr(request.app.state, "config_path", "open-deepwiki.yaml"),
        "debug_level": getattr(config, "debug_level", "INFO"),
        "java_codebase_dir": getattr(config, "java_codebase_dir", "./"),
        "project_name": getattr(config, "project_name", None),
        "default_project": None,
        "javadoc_min_meaningful_lines": getattr(config, "javadoc_min_meaningful_lines", 3),
        "chroma_anonymized_telemetry": getattr(config, "chroma_anonymized_telemetry", False),
        "startup_error": getattr(request.app.state, "startup_error", None),
        "has_openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "has_openai_chat_model": bool(os.getenv("OPENAI_CHAT_MODEL")),
        "openai_chat_model": os.getenv("OPENAI_CHAT_MODEL"),
        "openai_embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL"),
        "openai_chat_api_base": os.getenv("OPENAI_CHAT_API_BASE"),
        "openai_embedding_api_base": os.getenv("OPENAI_EMBEDDING_API_BASE"),
        "tiktoken_cache_dir": os.getenv("TIKTOKEN_CACHE_DIR"),
        "tiktoken_prefetch": bool(getattr(config, "tiktoken_prefetch", False)),
        "tiktoken_prefetch_encodings": getattr(config, "tiktoken_prefetch_encodings", None),
        "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        "chroma_collection": os.getenv("CHROMA_COLLECTION", "java_methods"),
        "loaded_project_scopes": [str(p) for p in loaded_scopes if p],
        "method_docs_loaded": int(loaded_total),
    }


@router.post("/query", response_model=List[QueryResult])
def query(request: Request, req: QueryRequest) -> List[QueryResult]:
    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot query embeddings-backed vector search.",
        )

    project = _normalize_project(req.project)
    retriever = _get_scoped_retriever(request, project=project)
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
                is_dependency=bool(meta.get("is_dependency", False)),
                called_from=meta.get("called_from"),
                page_content=doc.page_content,
            )
        )

    return results


@router.post("/ask", response_model=AskResponse)
def ask(request: Request, req: AskRequest) -> AskResponse:
    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot run chat completion.",
        )

    project = _normalize_project(req.project)
    retriever = _get_scoped_retriever(request, project=project)
    retriever.k = req.k
    docs = retriever.get_relevant_documents(req.question)

    # Always include a "big picture" overview when available.
    project_overviews = getattr(request.app.state, "project_overviews", None) or {}
    project_overview = project_overviews.get(project)

    context_results: List[QueryResult] = []
    context_blocks: List[str] = []

    if isinstance(project_overview, str) and project_overview.strip():
        context_blocks.append(f"### project_overview\n{project_overview.strip()}")
    for doc in docs:
        meta = doc.metadata or {}
        context_results.append(
            QueryResult(
                id=meta.get("id"),
                signature=meta.get("signature"),
                type=meta.get("type"),
                calls=meta.get("calls"),
                has_javadoc=meta.get("has_javadoc"),
                is_dependency=bool(meta.get("is_dependency", False)),
                called_from=meta.get("called_from"),
                page_content=doc.page_content,
            )
        )

        header = []
        if meta.get("signature"):
            header.append(f"signature={meta.get('signature')}")
        if meta.get("id"):
            header.append(f"id={meta.get('id')}")
        if meta.get("is_dependency"):
            header.append("dependency=true")
        if meta.get("called_from"):
            header.append(f"called_from={meta.get('called_from')}")

        header_text = " | ".join(header) if header else "context"
        context_blocks.append(f"### {header_text}\n{doc.page_content}")

    from utils.agent_factory import create_codebase_agent
    from utils.sqlite_checkpointer import SqliteCheckpointSaver

    system_prompt = (
        "You are a senior engineer assistant for a Java codebase. "
        "Prefer answering using the provided Context section. "
        "If the context is insufficient, you MAY use tools to inspect the codebase (browse_dir/get_file_contents/vector_search) "
        "to gather missing details. "
        "Conversation history is for continuity only. "
        "If you still cannot answer, say what you need next. "
        "Keep the answer concise and actionable."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{req.question}",
            "Context:",
            "\n\n".join(context_blocks) if context_blocks else "(no context)",
        ]
    )

    # Agent cache (per sandbox root).
    if not hasattr(request.app.state, "code_agents"):
        request.app.state.code_agents = {}

    # Checkpointer cache (per sqlite path).
    if not hasattr(request.app.state, "checkpointers"):
        request.app.state.checkpointers = {}

    session_id = req.session_id or uuid.uuid4().hex

    config = getattr(request.app.state, "config", None)
    code_root = getattr(config, "java_codebase_dir", "./") or "./"
    code_root_key = str(Path(code_root).expanduser().resolve())

    cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
    if cp_backend != "sqlite":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')",
        )
    cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
    cp_path_key = str(Path(cp_path).expanduser().resolve())

    checkpointers: Dict[str, Any] = request.app.state.checkpointers
    if cp_path_key not in checkpointers:
        checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
    checkpointer = checkpointers[cp_path_key]

    agents: Dict[str, Any] = request.app.state.code_agents
    agent_key = f"{code_root_key}::{project or ''}"
    if agent_key not in agents:
        graph_path = str(getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3") or "./project_graph.sqlite3")
        agents[agent_key] = create_codebase_agent(
            root_dir=code_root_key,
            retriever=retriever,
            checkpointer=checkpointer,
            project_graph_sqlite_path=graph_path,
            default_project=project or None,
            debug=(str(getattr(config, "debug_level", "")).upper() == "DEBUG"),
            system_prompt=system_prompt,
        )

    agent = agents[agent_key]

    try:
        agent_result = agent.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": project or "",
                }
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {e}")

    messages = (agent_result or {}).get("messages", []) if isinstance(agent_result, dict) else []
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    answer_text = getattr(last_ai, "content", None)
    if not isinstance(answer_text, str) or not answer_text.strip():
        answer_text = str(last_ai or agent_result)

    return AskResponse(
        session_id=session_id,
        project=project,
        answer=answer_text,
        context=context_results,
    )


@router.post("/index-directory", response_model=IndexDirectoryResponse)
def index_directory(request: Request, req: IndexDirectoryRequest) -> IndexDirectoryResponse:
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

    # Imports ici pour garder le module léger au chargement.
    from indexer import scan_java_methods
    from core.parsing.java_parser import JavaParser
    from core.rag.indexing import index_java_file_summaries, index_java_methods, index_project_overview
    from core.parsing.tree_sitter_setup import setup_java_language
    from utils.vectorstore import _get_vectorstore, _load_method_docs_map, delete_scoped_documents
    from core.rag.retriever import GraphEnrichedRetriever
    from core.project_graph import SqliteProjectGraphStore

    project = _normalize_project(req.project)

    try:
        setup_java_language()
        parser = JavaParser()
        methods = scan_java_methods(str(directory), parser)
        if project:
            for m in methods:
                m.project = project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan directory: {e}")

    if not methods:
        # Rien à indexer, mais on renvoie une réponse cohérente.
        return IndexDirectoryResponse(
            path=str(directory),
            project=project,
            indexed_methods=0,
            indexed_file_summaries=0,
            loaded_method_docs=len(getattr(request.app.state, "method_docs_map", {}) or {}),
        )

    vectorstore = getattr(request.app.state, "vectorstore", None)
    if vectorstore is None:
        try:
            vectorstore = _get_vectorstore()
            request.app.state.vectorstore = vectorstore
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to initialize vectorstore: {e}")

    try:
        if bool(req.reindex):
            delete_scoped_documents(vectorstore, project=project)

        indexed_map = index_java_methods(methods, vectorstore)

        config = getattr(request.app.state, "config", None)
        include_summaries = (
            bool(req.include_file_summaries)
            if req.include_file_summaries is not None
            else bool(getattr(config, "index_file_summaries", False))
        )
        indexed_summaries = 0
        if include_summaries:
            indexed_summaries = len(index_java_file_summaries(methods, vectorstore))

        # Build/update the project graph and persist a project overview doc.
        graph_path = str(getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3") or "./project_graph.sqlite3")
        graph_store = SqliteProjectGraphStore(sqlite_path=graph_path)
        graph_store.rebuild(project=project, methods=methods)
        overview = graph_store.overview_text(project=project)
        if overview:
            index_project_overview(project=project, overview_text=overview, vectorstore=vectorstore)

        persist = getattr(vectorstore, "persist", None)
        if callable(persist):
            persist()

        # Refresh caches for this project scope.
        method_docs_map = _load_method_docs_map(vectorstore, project=project)

        if not hasattr(request.app.state, "method_docs_maps"):
            request.app.state.method_docs_maps = {}
        request.app.state.method_docs_maps[project] = method_docs_map

        # Also keep a quick-access overview per project.
        if not hasattr(request.app.state, "project_overviews"):
            request.app.state.project_overviews = {}
        request.app.state.project_overviews[project] = overview

        if not hasattr(request.app.state, "retrievers"):
            request.app.state.retrievers = {}
        request.app.state.retrievers[project] = GraphEnrichedRetriever(
            vectorstore=vectorstore,
            method_docs_map=method_docs_map,
            k=int(os.getenv("RAG_K", "4")),
            project=project,
        )

        return IndexDirectoryResponse(
            path=str(directory),
            project=project,
            indexed_methods=len(indexed_map),
            indexed_file_summaries=int(indexed_summaries),
            loaded_method_docs=len(method_docs_map),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index directory: {e}")


@router.post("/generate-javadoc", response_model=GenerateJavadocJobResponse, status_code=202)
def generate_javadoc(request: Request, req: GenerateJavadocRequest) -> GenerateJavadocJobResponse:
    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot generate JavaDoc.",
        )

    directory = Path(req.path).expanduser()
    if not directory.is_absolute():
        directory = (Path.cwd() / directory).resolve()

    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {directory}")

    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    config = getattr(request.app.state, "config", None)
    min_lines = getattr(config, "javadoc_min_meaningful_lines", 3)

    try:
        job = JAVADOC_JOB_MANAGER.start(str(directory), min_meaningful_lines=int(min_lines))
        return GenerateJavadocJobResponse(job_id=job.job_id, root_dir=job.root_dir, status=job.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start JavaDoc generation: {e}")


@router.get("/generate-javadoc/jobs", response_model=List[JavadocJobInfo])
def list_generate_javadoc_jobs() -> List[JavadocJobInfo]:
    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    jobs = JAVADOC_JOB_MANAGER.list()
    return [
        JavadocJobInfo(
            job_id=j.job_id,
            root_dir=j.root_dir,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            stop_requested=bool(j.stop_requested),
            log_file=getattr(j, "log_file", None),
            summary=j.summary,
            error=j.error,
        )
        for j in jobs
    ]


@router.post("/generate-javadoc/jobs/{job_id}/stop", response_model=JavadocJobInfo)
def stop_generate_javadoc_job(job_id: str) -> JavadocJobInfo:
    from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

    try:
        j = JAVADOC_JOB_MANAGER.stop(job_id)
        return JavadocJobInfo(
            job_id=j.job_id,
            root_dir=j.root_dir,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            stop_requested=bool(j.stop_requested),
            log_file=getattr(j, "log_file", None),
            summary=j.summary,
            error=j.error,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/generate-javadoc/sessions/{session_id}/log", response_model=JavadocSessionLogResponse)
def read_javadoc_session_log(session_id: str) -> JavadocSessionLogResponse:
    """Read the postimplementation log for a JavaDoc generation session.

    Uses the in-memory job registry when available; falls back to searching for a
    log file whose filename ends with `_{session_id}.log`.
    """

    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    if not log_dir.exists() or not log_dir.is_dir():
        raise HTTPException(status_code=404, detail="Log directory not found")

    # Try from in-memory job manager first.
    log_path: Optional[Path] = None
    try:
        from core.documentation.javadoc_job_manager import JAVADOC_JOB_MANAGER

        jobs = JAVADOC_JOB_MANAGER.list()
        for j in jobs:
            if j.job_id == session_id and getattr(j, "log_file", None):
                log_path = Path(str(j.log_file)).expanduser().resolve()
                break
    except Exception:
        log_path = None

    # Fallback: find by filename suffix.
    if log_path is None:
        suffix = f"_{session_id}.log"
        for entry in log_dir.iterdir():
            if entry.is_file() and entry.name.startswith("postimplementation_") and entry.name.endswith(suffix):
                log_path = entry.resolve()
                break

    if log_path is None:
        raise HTTPException(status_code=404, detail="Session log not found")

    if log_dir not in log_path.parents and log_path != log_dir:
        raise HTTPException(status_code=400, detail="Invalid session log path")

    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="Session log not found")

    try:
        content = log_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session log: {e}")

    return JavadocSessionLogResponse(session_id=session_id, filename=log_path.name, content=content)


@router.get("/postimplementation-logs", response_model=PostImplementationLogListResponse)
def list_postimplementation_logs() -> PostImplementationLogListResponse:
    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    if not log_dir.exists():
        return PostImplementationLogListResponse(log_dir=str(log_dir), logs=[])
    if not log_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"POSTIMPLEMENTATION_LOG_DIR is not a directory: {log_dir}")

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


@router.get("/postimplementation-logs/{filename}", response_model=PostImplementationLogReadResponse)
def read_postimplementation_log(filename: str) -> PostImplementationLogReadResponse:
    safe = safe_log_filename(filename)
    if safe is None:
        raise HTTPException(status_code=400, detail="Invalid log filename")

    log_dir = Path(get_log_dir_from_env()).expanduser().resolve()
    path = (log_dir / safe).resolve()

    # Ensure the file resolves inside the log directory.
    if log_dir not in path.parents and path != log_dir:
        raise HTTPException(status_code=400, detail="Invalid log filename")

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")

    return PostImplementationLogReadResponse(filename=safe, content=content)
