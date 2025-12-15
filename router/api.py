from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from core.documentation.postimplementation_log import get_log_dir_from_env, safe_log_filename


router = APIRouter()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)


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


class IndexDirectoryResponse(BaseModel):
    path: str
    indexed_methods: int
    loaded_method_docs: int


class GenerateJavadocRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Chemin du répertoire à scanner (récursif).")


class GenerateJavadocResponse(BaseModel):
    root_dir: str
    files_scanned: int
    files_modified: int
    members_documented: int
    log_file: str


class PostImplementationLogInfo(BaseModel):
    filename: str
    size_bytes: int


class PostImplementationLogListResponse(BaseModel):
    log_dir: str
    logs: List[PostImplementationLogInfo]


class PostImplementationLogReadResponse(BaseModel):
    filename: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)


class AskResponse(BaseModel):
    answer: str
    context: List[QueryResult]


@router.get("/health")
def health(request: Request) -> Dict[str, Any]:
    config = getattr(request.app.state, "config", None)
    return {
        "status": "ok",
        "config_path": getattr(request.app.state, "config_path", "open-deepwiki.yaml"),
        "debug_level": getattr(config, "debug_level", "INFO"),
        "java_codebase_dir": getattr(config, "java_codebase_dir", "./"),
        "startup_error": getattr(request.app.state, "startup_error", None),
        "has_openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "has_openai_chat_model": bool(os.getenv("OPENAI_CHAT_MODEL")),
        "openai_chat_model": os.getenv("OPENAI_CHAT_MODEL"),
        "openai_embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL"),
        "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        "chroma_collection": os.getenv("CHROMA_COLLECTION", "java_methods"),
        "method_docs_loaded": len(getattr(request.app.state, "method_docs_map", {}) or {}),
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

    retriever = request.app.state.retriever
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

    retriever = request.app.state.retriever
    retriever.k = req.k
    docs = retriever.get_relevant_documents(req.question)

    context_results: List[QueryResult] = []
    context_blocks: List[str] = []
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

    from utils.chat import create_chat_model

    llm = create_chat_model()
    system_prompt = (
        "You are a senior engineer assistant for a Java codebase. "
        "Answer the user's question using ONLY the provided context. "
        "If the context is insufficient, say so explicitly and ask for the missing detail. "
        "Keep the answer concise and actionable."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{req.question}",
            "Context:",
            "\n\n".join(context_blocks) if context_blocks else "(no context)",
        ]
    )

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {e}")

    answer_text = getattr(response, "content", None)
    if not isinstance(answer_text, str):
        answer_text = str(response)

    return AskResponse(answer=answer_text, context=context_results)


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
    from core.rag.indexing import index_java_methods
    from core.parsing.tree_sitter_setup import setup_java_language
    from utils.vectorstore import _get_vectorstore, _load_method_docs_map
    from core.rag.retriever import GraphEnrichedRetriever

    try:
        setup_java_language()
        parser = JavaParser()
        methods = scan_java_methods(str(directory), parser)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan directory: {e}")

    if not methods:
        # Rien à indexer, mais on renvoie une réponse cohérente.
        return IndexDirectoryResponse(
            path=str(directory),
            indexed_methods=0,
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
        indexed_map = index_java_methods(methods, vectorstore)
        persist = getattr(vectorstore, "persist", None)
        if callable(persist):
            persist()

        # Recharge tout pour que l'enrichissement par graphe voit les nouvelles entrées.
        method_docs_map = _load_method_docs_map(vectorstore)
        request.app.state.method_docs_map = method_docs_map

        retriever = getattr(request.app.state, "retriever", None)
        if retriever is None:
            request.app.state.retriever = GraphEnrichedRetriever(
                vectorstore=vectorstore,
                method_docs_map=method_docs_map,
                k=int(os.getenv("RAG_K", "4")),
            )
        else:
            retriever.vectorstore = vectorstore
            retriever.method_docs_map = method_docs_map

        return IndexDirectoryResponse(
            path=str(directory),
            indexed_methods=len(indexed_map),
            loaded_method_docs=len(method_docs_map),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index directory: {e}")


@router.post("/generate-javadoc", response_model=GenerateJavadocResponse)
def generate_javadoc(request: Request, req: GenerateJavadocRequest) -> GenerateJavadocResponse:
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

    from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory

    try:
        summary = generate_missing_javadoc_in_directory(
            str(directory),
            log_dir=get_log_dir_from_env(),
        )
        return GenerateJavadocResponse(**summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate JavaDoc: {e}")


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
        except Exception:
            size = 0
        logs.append(PostImplementationLogInfo(filename=entry.name, size_bytes=size))

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
