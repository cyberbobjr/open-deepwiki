from __future__ import annotations

import os
from typing import Any, Dict, Optional

from langchain_openai import OpenAIEmbeddings


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def create_embeddings(base_url: Optional[str] = None) -> OpenAIEmbeddings:
    """Create OpenAI embeddings with optional custom base URL."""

    if base_url is None:
        base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
    if not base_url:
        raise ValueError(
            "Embeddings base URL is not set. Set OPENAI_EMBEDDING_API_BASE (or llm_api_base in YAML)."
        )

    model = os.getenv("OPENAI_EMBEDDING_MODEL")
    if not model:
        raise ValueError(
            "Embeddings model is not set. Set OPENAI_EMBEDDING_MODEL (or embeddings_model in YAML)."
        )

    kwargs: Dict[str, Any] = {
        "model": model,
    }

    # Compatibility note:
    # langchain_openai's OpenAIEmbeddings may send token-id arrays (list[int]) when
    # `check_embedding_ctx_length=True` (it tokenizes and passes tokens to the API).
    # Many OpenAI-compatible embedding servers only accept string inputs.
    # Default to string inputs for compatibility, and allow opting back in.
    kwargs["check_embedding_ctx_length"] = _env_bool(
        "OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH",
        default=False,
    )

    for key in ("base_url", "openai_api_base"):
        try:
            return OpenAIEmbeddings(**{**kwargs, key: base_url})
        except TypeError:
            continue

    raise TypeError(
        "OpenAIEmbeddings does not accept a base URL parameter (tried: base_url, openai_api_base)."
    )
