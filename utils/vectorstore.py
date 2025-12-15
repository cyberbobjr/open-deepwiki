from __future__ import annotations

import os
from typing import Any, Dict

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.rag.embeddings import create_embeddings


def _get_vectorstore() -> Chroma:
    persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "java_methods")

    base_url = os.getenv("OPENAI_API_BASE")
    embeddings = create_embeddings(base_url)

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )


def _load_method_docs_map(vectorstore: Chroma) -> Dict[str, Document]:
    """Load all stored documents into an id -> Document map.

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
            if "id" not in metadata and doc_id:
                metadata["id"] = doc_id
            method_id = metadata.get("id")
            if not method_id:
                continue
            method_docs_map[method_id] = Document(page_content=doc_text or "", metadata=metadata)
        return method_docs_map

    # Preferred: LangChain wrapper method.
    try:
        result = vectorstore.get(include=["documents", "metadatas"])  # type: ignore[attr-defined]
        if isinstance(result, dict):
            return _normalize_rows(result)
    except Exception:
        pass

    # Fallback: reach into the underlying Chroma collection.
    try:
        collection = getattr(vectorstore, "_collection")
        result = collection.get(include=["documents", "metadatas"])  # type: ignore[no-any-return]
        if isinstance(result, dict):
            return _normalize_rows(result)
    except Exception:
        pass

    return {}
