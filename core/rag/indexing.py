from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.parsing.java_parser import JavaMethod


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


def index_java_methods(methods: List[JavaMethod], vectorstore: Chroma) -> Dict[str, Document]:
    """Index Java methods into the vector store.

    Notes:
    - Chroma metadata must contain primitive types.
    - `calls` is serialized as a comma-separated string (tests rely on this).
    """

    documents: List[Document] = []
    ids: List[str] = []
    method_docs_map: Dict[str, Document] = {}

    for method in methods:
        project: Optional[str] = getattr(method, "project", None)
        file_path: Optional[str] = getattr(method, "file_path", None)
        start_line: Optional[int] = getattr(method, "start_line", None)
        end_line: Optional[int] = getattr(method, "end_line", None)

        scoped_id = f"{project}::{method.id}" if project else method.id

        content_parts = [
            f"Signature: {method.signature}",
            f"Type: {method.type}",
        ]

        if method.javadoc:
            content_parts.append(f"Documentation: {method.javadoc}")

        if method.calls:
            content_parts.append(f"Calls: {', '.join(method.calls)}")

        content_parts.append(f"Code:\n{method.code}")

        content = "\n\n".join(content_parts)

        calls_serialized = ", ".join(sorted(method.calls))

        doc = Document(
            page_content=content,
            metadata={
                "id": method.id,
                "scoped_id": scoped_id,
                "signature": method.signature,
                "type": method.type,
                "calls": calls_serialized,
                "has_javadoc": method.javadoc is not None,
                "project": project,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "doc_type": "java_method",
            },
        )

        documents.append(doc)
        ids.append(scoped_id)
        method_docs_map[method.id] = doc

    _safe_add_documents(vectorstore, documents, ids=ids)

    return method_docs_map


def index_java_file_summaries(methods: List[JavaMethod], vectorstore: Chroma) -> Dict[Tuple[Optional[str], str], Document]:
    """Index one summary document per Java file.

    Summary is heuristic (no LLM). It helps RAG answer file-level questions.
    """

    by_file: Dict[str, List[JavaMethod]] = {}
    for m in methods:
        fp = getattr(m, "file_path", None) or "(unknown)"
        by_file.setdefault(fp, []).append(m)

    documents: List[Document] = []
    ids: List[str] = []
    out: Dict[Tuple[Optional[str], str], Document] = {}

    for file_path, file_methods in by_file.items():
        project: Optional[str] = getattr(file_methods[0], "project", None)
        scoped_id = f"{project}::file::{file_path}" if project else f"file::{file_path}"

        # Stable, compact summary text.
        sigs = [m.signature for m in file_methods if m.signature]
        sigs = list(dict.fromkeys(sigs))  # preserve order, de-dup
        calls: List[str] = []
        for m in file_methods:
            calls.extend(list(m.calls or []))
        calls = sorted(set(calls))

        content_parts = [
            f"File: {file_path}",
        ]
        if project:
            content_parts.append(f"Project: {project}")

        content_parts.append(f"Methods: {len(file_methods)}")
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
                "doc_type": "java_file_summary",
            },
        )
        documents.append(doc)
        ids.append(scoped_id)
        out[(project, file_path)] = doc

    _safe_add_documents(vectorstore, documents, ids=ids)
    return out


def index_project_overview(
    *,
    project: Optional[str],
    overview_text: str,
    vectorstore: Chroma,
    indexed_path: Optional[str] = None,
    indexed_at: Optional[str] = None,
) -> Document:
    """Index a single "project overview" document for a project scope.

    This document is meant to provide an always-available big-picture context that can
    be injected into `/ask` prompts.
    """

    scoped_id = f"{project}::project::overview" if project else "project::overview"

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


def index_generated_markdown_docs(
    *,
    project: Optional[str],
    docs_root: Path,
    vectorstore: Chroma,
) -> List[Document]:
    """Index generated markdown documentation into the vector store.

    This is intended for files produced by:
    - `core/documentation/feature_extractor.py`
    - `core/documentation/site_generator.py`

    Args:
        project: Optional project scope name. If provided, it is stored in metadata
            and used to build stable scoped ids.
        docs_root: Directory containing generated markdown files (recursively).
        vectorstore: Chroma vector store.

    Returns:
        The list of indexed `Document` instances (empty if nothing was indexed).
    """

    root = Path(docs_root).expanduser()
    if not root.exists() or not root.is_dir():
        return []

    documents: List[Document] = []
    ids: List[str] = []

    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            # Best-effort; skip unreadable generated docs.
            continue

        try:
            rel = path.relative_to(root).as_posix()
        except Exception:
            rel = path.name

        scoped_id = f"{project}::docs::{rel}" if project else f"docs::{rel}"

        doc = Document(
            page_content=str(text or "").strip(),
            metadata={
                "scoped_id": scoped_id,
                "project": project,
                "doc_type": "generated_markdown",
                "doc_relpath": rel,
                "doc_path": str(path),
            },
        )

        documents.append(doc)
        ids.append(scoped_id)

    _safe_add_documents(vectorstore, documents, ids=ids)
    return documents
