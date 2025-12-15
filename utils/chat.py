from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Prefer `langchain-openai` for OpenAI SDK v1 compatibility.
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    try:
        from langchain_community.chat_models import ChatOpenAI  # type: ignore
    except Exception:  # pragma: no cover
        from langchain.chat_models import ChatOpenAI  # type: ignore


def create_chat_model(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> Any:
    """Create a chat LLM.

    Uses environment variables by default:
    - OPENAI_CHAT_MODEL (fallback if `model` is None)
    - OPENAI_API_KEY
    - OPENAI_API_BASE (fallback if `base_url` is None)
    """

    selected_model = model or os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
    selected_base_url = base_url or os.getenv("OPENAI_API_BASE")

    kwargs: Dict[str, Any] = {
        "model": selected_model,
        "temperature": temperature,
    }

    if selected_base_url:
        for key in ("base_url", "openai_api_base"):
            try:
                return ChatOpenAI(**{**kwargs, key: selected_base_url})
            except TypeError:
                continue

    return ChatOpenAI(**kwargs)
