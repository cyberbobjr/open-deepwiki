from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel


DEFAULT_CONFIG_PATH = "open-deepwiki.yaml"


class AppConfig(BaseModel):
    debug_level: str = "INFO"
    java_codebase_dir: str = "./"

    # FastAPI / Uvicorn
    api_port: int = 8000

    # LLM configuration (for embeddings + chat).
    # This repo currently uses embeddings (Chroma + OpenAIEmbeddings) and may
    # also use a chat model for answer generation.
    embeddings_model: Optional[str] = None
    chat_model: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None


def apply_config_to_env(config: AppConfig) -> None:
    """Apply config values to environment variables if not already set.

    This keeps the rest of the code using the same env vars:
    - OPENAI_API_KEY
    - OPENAI_API_BASE
    - OPENAI_EMBEDDING_MODEL
    - OPENAI_CHAT_MODEL (for future chat usage)
    """

    if getattr(config, "llm_api_key", None) and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = str(config.llm_api_key)

    if getattr(config, "llm_api_base", None) and not os.getenv("OPENAI_API_BASE"):
        os.environ["OPENAI_API_BASE"] = str(config.llm_api_base)

    if getattr(config, "embeddings_model", None) and not os.getenv("OPENAI_EMBEDDING_MODEL"):
        os.environ["OPENAI_EMBEDDING_MODEL"] = str(config.embeddings_model)

    if getattr(config, "chat_model", None) and not os.getenv("OPENAI_CHAT_MODEL"):
        os.environ["OPENAI_CHAT_MODEL"] = str(config.chat_model)


def load_config(path: Optional[str] = None) -> AppConfig:
    """Load application configuration from YAML.

    Precedence:
    1) explicit `path`
    2) env var `OPEN_DEEPWIKI_CONFIG`
    3) `open-deepwiki.yaml` in the current working directory

    Missing config file falls back to defaults.
    """

    config_path = path or os.getenv("OPEN_DEEPWIKI_CONFIG") or DEFAULT_CONFIG_PATH

    if not os.path.exists(config_path):
        return AppConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return AppConfig()

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid YAML config (expected mapping), got: {type(raw).__name__}")

    data: Dict[str, Any] = dict(raw)
    return AppConfig(**data)


def configure_logging(debug_level: str) -> None:
    level_name = (debug_level or "INFO").upper().strip()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid debug_level: {debug_level!r} (expected DEBUG/INFO/WARNING/ERROR)")

    logging.basicConfig(level=level)
