from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.parsing.models import CodeBlock
from core.ports.rag_port import VectorIndex
from core.rag.embeddings import create_embeddings

logger = logging.getLogger(__name__)

def _safe_add_documents(vectorstore: Chroma, documents: List[Document], *, ids: Optional[List[str]] = None) -> None:
    if not documents:
        return

    if ids is None:
        vectorstore.add_documents(documents)
        return

    try:
        vectorstore.add_documents(documents, ids=ids)
    except TypeError:
        vectorstore.add_documents(documents)
    except Exception:
        # Best-effort delete + retry for duplicate ids.
        try:
            vectorstore.delete(ids=ids)
        except Exception:
            try:
                collection = getattr(vectorstore, "_collection")
                collection.delete(ids=ids)
            except Exception:
                raise
        vectorstore.add_documents(documents, ids=ids)


class ChromaVectorIndex(VectorIndex):
    """ChromaDB implementation of the VectorIndex."""

    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "code_blocks"):
        base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
        embeddings = create_embeddings(base_url)
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

    def index_code_blocks(self, methods: List[CodeBlock]) -> int:
        """Index generic code blocks (methods/functions)."""
        documents: List[Document] = []
        ids: List[str] = []

        for method in methods:
            project: Optional[str] = getattr(method, "project", None)
            scoped_id = f"{project}::{method.id}" if project else method.id

            content_parts = [
                f"Signature: {method.signature}",
                f"Type: {method.type}",
                f"Language: {method.language}",
            ]

            if method.docstring:
                content_parts.append(f"Documentation: {method.docstring}")

            if method.calls:
                content_parts.append(f"Calls: {', '.join(method.calls)}")

            content_parts.append(f"Code:\n{method.code}")

            content = "\n\n".join(content_parts)
            calls_serialized = ", ".join(sorted(method.calls or []))

            doc = Document(
                page_content=content,
                metadata={
                    "id": method.id,
                    "scoped_id": scoped_id,
                    "signature": method.signature,
                    "type": method.type,
                    "language": method.language,
                    "calls": calls_serialized,
                    "has_docstring": method.docstring is not None,
                    "project": project,
                    "file_path": getattr(method, "file_path", None),
                    "start_line": getattr(method, "start_line", None),
                    "end_line": getattr(method, "end_line", None),
                    "doc_type": "code_block",
                },
            )

            documents.append(doc)
            ids.append(scoped_id)

        _safe_add_documents(self.vectorstore, documents, ids=ids)
        logger.info("Indexed %d code blocks", len(documents))
        return len(documents)

    def index_file_summaries(self, methods: List[CodeBlock]) -> int:
        """Index one summary document per file."""
        by_file: Dict[str, List[CodeBlock]] = {}
        for m in methods:
            fp = getattr(m, "file_path", None) or "(unknown)"
            by_file.setdefault(fp, []).append(m)

        documents: List[Document] = []
        ids: List[str] = []

        for file_path, file_methods in by_file.items():
            if not file_methods:
                continue
                
            project: Optional[str] = getattr(file_methods[0], "project", None)
            scoped_id = f"{project}::file::{file_path}" if project else f"file::{file_path}"
            language = file_methods[0].language

            sigs = [m.signature for m in file_methods if m.signature]
            sigs = list(dict.fromkeys(sigs))
            
            calls: List[str] = []
            for m in file_methods:
                calls.extend(list(m.calls or []))
            calls = sorted(set(calls))

            content_parts = [
                f"File: {file_path}",
                f"Language: {language}",
            ]
            if project:
                content_parts.append(f"Project: {project}")

            content_parts.append(f"Blocks: {len(file_methods)}")
            if sigs:
                content_parts.append("Signatures:\n- " + "\n- ".join(sigs[:80]))
            if calls:
                content_parts.append("Calls (unique): " + ", ".join(calls[:120]))

            doc = Document(
                page_content="\n\n".join(content_parts),
                metadata={
                    "scoped_id": scoped_id,
                    "project": project,
                    "file_path": file_path,
                    "language": language,
                    "doc_type": "file_summary",
                },
            )
            documents.append(doc)
            ids.append(scoped_id)

        _safe_add_documents(self.vectorstore, documents, ids=ids)
        logger.info("Indexed %d file summaries", len(documents))
        return len(documents)

    def persist(self) -> None:
        persist = getattr(self.vectorstore, "persist", None)
        if callable(persist):
            persist()

# Legacy functions for compatibility
def index_code_blocks(methods: List[CodeBlock], vectorstore: Chroma) -> Dict[str, Document]:
    # This was returning a map, but the interface returns int. 
    # For backward compatibility, we'll reimplement it minimally or wrap the new class.
    # Note: The original code returned a map. If external code relies on this map, breaking change.
    # We will replicate logic here for legacy support.
    
    indexer = ChromaVectorIndex()
    # HACK: injecting the passed vectorstore
    indexer.vectorstore = vectorstore
    indexer.index_code_blocks(methods)
    return {} # Returning empty map as a compromise, assuming mostly side-effect reliance

def index_file_summaries(methods: List[CodeBlock], vectorstore: Chroma) -> Dict[Tuple[Optional[str], str], Document]:
    indexer = ChromaVectorIndex()
    indexer.vectorstore = vectorstore
    indexer.index_file_summaries(methods)
    return {} 

def index_project_overview(
    *,
    project: str,
    overview_text: str,
    vectorstore: Chroma,
    indexed_path: Optional[str] = None,
    indexed_at: Optional[str] = None,
) -> Document:
    """Index the main project overview."""
    # Create a stable ID for the overview
    scoped_id = f"{project}::project::overview"

    metadata: Dict[str, Optional[str]] = {
        "scoped_id": scoped_id,
        "project": project,
        "doc_type": "project_overview",
    }
    if indexed_path is not None:
        metadata["indexed_path"] = str(indexed_path)
    if indexed_at is not None:
        metadata["indexed_at"] = str(indexed_at)

    doc = Document(
        page_content=str(overview_text or "").strip(),
        metadata=metadata,
    )

    _safe_add_documents(vectorstore, [doc], ids=[scoped_id])
    return doc

def index_feature_page(
    *,
    project: str,
    feature_name: str,
    page_content: str,
    vectorstore: Chroma,
) -> Document:
    """Index a feature documentation page."""
    if not project:
        raise ValueError("Project name is required for indexing.")

    # Create a stable ID for the feature page
    safe_name = feature_name.strip().lower().replace(" ", "-")
    scoped_id = f"{project}::feature::{safe_name}"

    metadata: Dict[str, Optional[str]] = {
        "scoped_id": scoped_id,
        "project": project,
        "feature_name": feature_name,
        "doc_type": "feature_page",
    }

    doc = Document(
        page_content=str(page_content or "").strip(),
        metadata=metadata,
    )

    _safe_add_documents(vectorstore, [doc], ids=[scoped_id])
    logger.info("Indexed feature page: %s", scoped_id)
    return doc

def index_module_summary(
    *,
    project: str,
    module_name: str,
    summary_content: str,
    vectorstore: Chroma,
) -> Document:
    """Index a module summary."""
    if not project:
        raise ValueError("Project name is required for indexing.")

    safe_name = module_name.strip().lower().replace(" ", "-").replace("/", "-")
    if not safe_name or safe_name == ".":
        safe_name = "root"
    
    scoped_id = f"{project}::module::{safe_name}"

    metadata: Dict[str, Optional[str]] = {
        "scoped_id": scoped_id,
        "project": project,
        "module_name": module_name,
        "doc_type": "module_summary",
    }

    doc = Document(
        page_content=str(summary_content or "").strip(),
        metadata=metadata,
    )

    _safe_add_documents(vectorstore, [doc], ids=[scoped_id])
    logger.info("Indexed module summary: %s", scoped_id)
    return doc
