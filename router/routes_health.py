from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request) -> Dict[str, Any]:
    """Lightweight health/status endpoint."""

    config = getattr(request.app.state, "config", None)
    method_maps = getattr(request.app.state, "method_docs_maps", None) or {}
    loaded_scopes = list(method_maps.keys()) if isinstance(method_maps, dict) else []
    loaded_total = 0
    if isinstance(method_maps, dict):
        for _, m in method_maps.items():
            try:
                loaded_total += len(m or {})
            except Exception:
                pass

    return {
        "status": "ok",
        "config_path": getattr(request.app.state, "config_path", "open-deepwiki.yaml"),
        "debug_level": getattr(config, "debug_level", "INFO"),
        "java_codebase_dir": getattr(config, "java_codebase_dir", "./"),
        "project_name": getattr(config, "project_name", None),
        "default_project": None,

        "chroma_anonymized_telemetry": getattr(config, "chroma_anonymized_telemetry", False),
        "startup_error": getattr(request.app.state, "startup_error", None),
        "has_openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "has_openai_chat_model": bool(os.getenv("OPENAI_CHAT_MODEL")),
        "openai_chat_model": os.getenv("OPENAI_CHAT_MODEL"),
        "openai_embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL"),
        "openai_chat_api_base": os.getenv("OPENAI_CHAT_API_BASE"),
        "openai_embedding_api_base": os.getenv("OPENAI_EMBEDDING_API_BASE"),
        "tiktoken_cache_dir": os.getenv("TIKTOKEN_CACHE_DIR"),
        "tiktoken_prefetch": bool(getattr(config, "tiktoken_prefetch", False)),
        "tiktoken_prefetch_encodings": getattr(config, "tiktoken_prefetch_encodings", None),
        "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        "chroma_collection": os.getenv("CHROMA_COLLECTION", "java_methods"),
        "loaded_project_scopes": [str(p) for p in loaded_scopes if p],
        "method_docs_loaded": int(loaded_total),
    }
