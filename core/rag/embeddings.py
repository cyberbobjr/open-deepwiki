from __future__ import annotations

import os
from typing import Any, Dict, Optional

from langchain_openai import OpenAIEmbeddings


def create_embeddings(base_url: Optional[str] = None) -> OpenAIEmbeddings:
    """Create OpenAI embeddings with optional custom base URL."""

    if base_url is None:
        base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
    if not base_url:
        raise ValueError(
            "Embeddings base URL is not set. Set OPENAI_EMBEDDING_API_BASE (or embeddings_api_base in YAML)."
        )

    model = os.getenv("OPENAI_EMBEDDING_MODEL")
    if not model:
        raise ValueError(
            "Embeddings model is not set. Set OPENAI_EMBEDDING_MODEL (or embeddings_model in YAML)."
        )

    kwargs: Dict[str, Any] = {
        "model": model,
    }

    for key in ("base_url", "openai_api_base"):
        try:
            return OpenAIEmbeddings(**{**kwargs, key: base_url})
        except TypeError:
            continue

    raise TypeError(
        "OpenAIEmbeddings does not accept a base URL parameter (tried: base_url, openai_api_base)."
    )
