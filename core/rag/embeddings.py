from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Prefer `langchain-openai` for OpenAI SDK v1 compatibility.
try:
    from langchain_openai import OpenAIEmbeddings  # type: ignore
except Exception:  # pragma: no cover
    try:
        from langchain_community.embeddings.openai import OpenAIEmbeddings  # type: ignore
    except Exception:  # pragma: no cover
        from langchain.embeddings.openai import OpenAIEmbeddings  # type: ignore


def create_embeddings(base_url: Optional[str] = None) -> OpenAIEmbeddings:
    """Create OpenAI embeddings with optional custom base URL."""

    kwargs: Dict[str, Any] = {
        "model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
    }

    if base_url:
        for key in ("base_url", "openai_api_base"):
            try:
                return OpenAIEmbeddings(**{**kwargs, key: base_url})
            except TypeError:
                continue

    return OpenAIEmbeddings(**kwargs)
