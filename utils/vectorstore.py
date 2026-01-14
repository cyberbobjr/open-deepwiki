from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.rag.embeddings import create_embeddings


def _get_vectorstore() -> Chroma:
    persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "code_blocks")

    base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
    embeddings = create_embeddings(base_url)

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )


def _load_method_docs_map(
    vectorstore: Chroma,
    *,
    project: Optional[str] = None,
) -> Dict[str, Document]:
    """Load stored *method* documents into a scoped_id -> Document map.

    This supports dependency enrichment across requests.

    Note: For large collections this is expensive; this repo currently targets
    small-to-medium demos and local usage.
    """

    def _normalize_rows(result: Dict[str, Any]) -> Dict[str, Document]:
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        ids = result.get("ids") or []

        method_docs_map: Dict[str, Document] = {}
        for doc_text, meta, doc_id in zip(docs, metas, ids):
            metadata = dict(meta or {})
            # Prefer explicit metadata keys written at index-time.
            # Fallback to the Chroma row id when present.
            scoped_id = metadata.get("scoped_id") or (doc_id if doc_id else None)
            if not scoped_id:
                continue

            # Keep only Java method docs for graph enrichment.
            if metadata.get("doc_type") and metadata.get("doc_type") != "java_method":
                continue
            if project is not None and metadata.get("project") != project:
                continue

            method_docs_map[str(scoped_id)] = Document(page_content=doc_text or "", metadata=metadata)
        return method_docs_map

    def _get_where() -> Optional[Dict[str, Any]]:
        if project is None:
            return None
        return {"project": project}

    where = _get_where()

    # Preferred: LangChain wrapper method.
    try:
        # Some versions accept `where`, some don't.
        try:
            result = vectorstore.get(include=["documents", "metadatas"], where=where)  # type: ignore[attr-defined]
        except TypeError:
            result = vectorstore.get(include=["documents", "metadatas"])  # type: ignore[attr-defined]
        if isinstance(result, dict):
            return _normalize_rows(result)
    except Exception:
        pass

    # Fallback: reach into the underlying Chroma collection.
    try:
        collection = getattr(vectorstore, "_collection")
        try:
            result = collection.get(include=["documents", "metadatas"], where=where)  # type: ignore[no-any-return]
        except TypeError:
            result = collection.get(include=["documents", "metadatas"])  # type: ignore[no-any-return]
        if isinstance(result, dict):
            return _normalize_rows(result)
    except Exception:
        pass

    return {}


def delete_scoped_documents(vectorstore: Chroma, *, project: Optional[str]) -> None:
    """Delete all documents for a project scope.

    If project is None, deletes the entire collection (use with care).
    """

    where: Optional[Dict[str, Any]]
    if project is None:
        where = None
    else:
        where = {"project": project}

    # Preferred wrapper.
    try:
        if where is None:
            # Some implementations treat `where=None` as "delete all".
            vectorstore.delete(where={})  # type: ignore[arg-type]
        else:
            vectorstore.delete(where=where)  # type: ignore[arg-type]
        return
    except Exception:
        pass

    # Fallback to underlying collection.
    try:
        collection = getattr(vectorstore, "_collection")
        if where is None:
            collection.delete(where={})
        else:
            collection.delete(where=where)
    except Exception:
        # If deletion isn't supported, callers can still reindex into a new collection.
        raise


def safe_add_documents(vectorstore: Chroma, documents: List[Document], *, ids: Optional[List[str]] = None) -> None:
    """Add documents with best-effort stable ids.

    If the underlying store rejects duplicate ids, this attempts to delete and retry.
    """

    if not documents:
        return

    if ids is None:
        vectorstore.add_documents(documents)
        return

    try:
        vectorstore.add_documents(documents, ids=ids)
        return
    except TypeError:
        vectorstore.add_documents(documents)
        return
    except Exception:
        # Retry by deleting the conflicting ids first.
        try:
            vectorstore.delete(ids=ids)
        except Exception:
            try:
                collection = getattr(vectorstore, "_collection")
                collection.delete(ids=ids)
            except Exception:
                raise
        vectorstore.add_documents(documents, ids=ids)

