from __future__ import annotations

import os
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI


def create_chat_model(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> Any:
    """Create a chat LLM.

    Uses environment variables by default:
    - OPENAI_CHAT_MODEL (fallback if `model` is None)
    - OPENAI_API_KEY
    - OPENAI_CHAT_API_BASE (fallback if `base_url` is None)
    """

    selected_model = model or os.getenv("OPENAI_CHAT_MODEL")
    if not selected_model:
        raise ValueError(
            "Chat model is not set. Set OPENAI_CHAT_MODEL (or chat_model in YAML)."
        )

    selected_base_url = base_url or os.getenv("OPENAI_CHAT_API_BASE")
    if not selected_base_url:
        raise ValueError(
            "Chat base URL is not set. Set OPENAI_CHAT_API_BASE (or llm_api_base in YAML)."
        )

    kwargs: Dict[str, Any] = {
        "model": selected_model,
        "temperature": temperature,
    }

    for key in ("base_url", "openai_api_base"):
        try:
            return ChatOpenAI(**{**kwargs, key: selected_base_url})
        except TypeError:
            continue

    raise TypeError(
        "ChatOpenAI does not accept a base URL parameter (tried: base_url, openai_api_base)."
    )
