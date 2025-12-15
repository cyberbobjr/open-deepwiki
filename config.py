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

    # Optional project scope name.
    # When set, all indexed documents get metadata.project=<project_name>.
    project_name: Optional[str] = None

    # FastAPI / Uvicorn
    api_port: int = 8000

    # JavaDoc generation
    # Existing JavaDoc blocks with fewer than this number of "meaningful" content lines
    # will be regenerated (replaced). See core/documentation/javadoc_generator.py.
    javadoc_min_meaningful_lines: int = 3

    # Chroma
    # Chroma enables anonymized telemetry by default; set this to False to opt out.
    # This maps to the `ANONYMIZED_TELEMETRY` environment variable.
    chroma_anonymized_telemetry: bool = False

    # Indexing (optional)
    # If true, indexing can add one extra "file summary" document per Java file.
    # This summary is heuristic (no LLM required) and is meant to help RAG.
    index_file_summaries: bool = False

    # Agent persistence (LangGraph checkpointer)
    # Supported values: "sqlite".
    checkpointer_backend: str = "sqlite"
    checkpointer_sqlite_path: str = "./checkpoints.sqlite3"

    # LLM configuration (for embeddings + chat).
    # This repo currently uses embeddings (Chroma + OpenAIEmbeddings) and may
    # also use a chat model for answer generation.
    embeddings_model: Optional[str] = None
    chat_model: Optional[str] = None
    llm_api_base: Optional[str] = None
    # Optional overrides if you want different gateways for embeddings vs chat.
    # If not set, they are derived from `llm_api_base` (NOT from OPENAI_API_BASE).
    embeddings_api_base: Optional[str] = None
    chat_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None

    # Embeddings input compatibility
    # If True, langchain_openai may tokenize long inputs and send token-id arrays to the
    # embeddings API. Some OpenAI-compatible servers only accept string inputs.
    # Default is False for compatibility.
    embeddings_check_ctx_length: bool = False

    # SSL / TLS
    # Path to a PEM file containing root CA certificates to trust for outbound HTTPS.
    # When set, this is applied to common env vars used by requests/urllib3 and many
    # OpenSSL-based clients.
    ssl_ca_file: Optional[str] = None

    # Outbound network proxy settings (for downloads and API calls).
    # These map to standard environment variables respected by requests/urllib and
    # many libraries (including tiktoken downloads via urllib).
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = None

    # Optional: where tiktoken stores downloaded/cached encoding files.
    # Maps to `TIKTOKEN_CACHE_DIR`.
    # Note: tiktoken stores downloads under `<cache_dir>/<sha1(url)>`, not by original filename.
    tiktoken_cache_dir: Optional[str] = None

    # Optional: prefetch tiktoken encodings at startup to force download/caching.
    # When enabled, `tiktoken.get_encoding(name)` is called for each encoding.
    # If `tiktoken_prefetch_encodings` is not set, defaults to ["cl100k_base"].
    tiktoken_prefetch: bool = False
    tiktoken_prefetch_encodings: Optional[list[str]] = None


def apply_config_to_env(config: AppConfig) -> None:
    """Apply config values to environment variables if not already set.

    This keeps the rest of the code using env vars, with optional per-feature base URLs:
    - OPENAI_API_KEY
    - OPENAI_API_BASE (default/fallback)
    - OPENAI_EMBEDDING_API_BASE (optional override for embeddings)
    - OPENAI_CHAT_API_BASE (optional override for chat)
    - OPENAI_EMBEDDING_MODEL
    - OPENAI_CHAT_MODEL
    """

    if getattr(config, "llm_api_key", None) and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = str(config.llm_api_key)

    if getattr(config, "llm_api_base", None) and not os.getenv("OPENAI_API_BASE"):
        os.environ["OPENAI_API_BASE"] = str(config.llm_api_base)

    # Endpoints: prefer per-feature overrides, otherwise derive from llm_api_base.
    # Strict: never derive from OPENAI_API_BASE (only from llm_api_base in YAML).
    llm_api_base = getattr(config, "llm_api_base", None)

    embeddings_api_base = getattr(config, "embeddings_api_base", None) or llm_api_base
    if embeddings_api_base and not os.getenv("OPENAI_EMBEDDING_API_BASE"):
        os.environ["OPENAI_EMBEDDING_API_BASE"] = str(embeddings_api_base)

    chat_api_base = getattr(config, "chat_api_base", None) or llm_api_base
    if chat_api_base and not os.getenv("OPENAI_CHAT_API_BASE"):
        os.environ["OPENAI_CHAT_API_BASE"] = str(chat_api_base)

    if getattr(config, "embeddings_model", None) and not os.getenv("OPENAI_EMBEDDING_MODEL"):
        os.environ["OPENAI_EMBEDDING_MODEL"] = str(config.embeddings_model)

    # Controls whether embeddings can send token-id arrays vs strings.
    # Consumed by core.rag.embeddings.create_embeddings().
    if getattr(config, "embeddings_check_ctx_length", None) is not None and not os.getenv(
        "OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH"
    ):
        os.environ["OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH"] = (
            "true" if bool(config.embeddings_check_ctx_length) else "false"
        )

    if getattr(config, "chat_model", None) and not os.getenv("OPENAI_CHAT_MODEL"):
        os.environ["OPENAI_CHAT_MODEL"] = str(config.chat_model)

    # Outbound proxy configuration.
    # Respect already-set env vars so ops can override config.
    http_proxy = getattr(config, "http_proxy", None)
    if http_proxy:
        if not os.getenv("http_proxy"):
            os.environ["http_proxy"] = str(http_proxy)
        if not os.getenv("HTTP_PROXY"):
            os.environ["HTTP_PROXY"] = str(http_proxy)

    https_proxy = getattr(config, "https_proxy", None)
    if https_proxy:
        if not os.getenv("https_proxy"):
            os.environ["https_proxy"] = str(https_proxy)
        if not os.getenv("HTTPS_PROXY"):
            os.environ["HTTPS_PROXY"] = str(https_proxy)

    no_proxy = getattr(config, "no_proxy", None)
    if no_proxy:
        if not os.getenv("no_proxy"):
            os.environ["no_proxy"] = str(no_proxy)
        if not os.getenv("NO_PROXY"):
            os.environ["NO_PROXY"] = str(no_proxy)

    # tiktoken cache directory (helps in locked-down environments).
    tiktoken_cache_dir = getattr(config, "tiktoken_cache_dir", None)
    if tiktoken_cache_dir and not os.getenv("TIKTOKEN_CACHE_DIR"):
        os.environ["TIKTOKEN_CACHE_DIR"] = str(tiktoken_cache_dir)

    # SSL CA bundle override for outbound HTTPS.
    # Prefer respecting already-set env vars so ops can override config.
    ssl_ca_file = getattr(config, "ssl_ca_file", None)
    if ssl_ca_file:
        if not os.path.exists(str(ssl_ca_file)):
            logging.getLogger(__name__).warning(
                "Configured ssl_ca_file does not exist: %s", ssl_ca_file
            )

        if not os.getenv("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = str(ssl_ca_file)
        if not os.getenv("REQUESTS_CA_BUNDLE"):
            os.environ["REQUESTS_CA_BUNDLE"] = str(ssl_ca_file)
        if not os.getenv("CURL_CA_BUNDLE"):
            os.environ["CURL_CA_BUNDLE"] = str(ssl_ca_file)

    # Chroma telemetry opt-out (https://docs.trychroma.com/telemetry)
    if getattr(config, "chroma_anonymized_telemetry", None) is not None and not os.getenv(
        "ANONYMIZED_TELEMETRY"
    ):
        os.environ["ANONYMIZED_TELEMETRY"] = "True" if bool(config.chroma_anonymized_telemetry) else "False"


def prefetch_tiktoken_encodings(config: AppConfig) -> None:
    """Force-download/cache tiktoken encodings.

    This is useful in locked-down environments where you want downloads to happen
    at startup (with proxies/CA configured) instead of lazily later.
    """

    if not bool(getattr(config, "tiktoken_prefetch", False)):
        return

    encodings = getattr(config, "tiktoken_prefetch_encodings", None) or ["cl100k_base"]

    logging.getLogger(__name__).info(
        "tiktoken prefetch enabled (encodings=%s, TIKTOKEN_CACHE_DIR=%s)",
        encodings,
        os.getenv("TIKTOKEN_CACHE_DIR"),
    )

    try:
        import tiktoken  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "tiktoken_prefetch is enabled but 'tiktoken' could not be imported. "
            "Install it (pip install tiktoken) or disable tiktoken_prefetch."
        ) from e

    for name in encodings:
        logging.getLogger(__name__).info("Prefetching tiktoken encoding: %s", name)
        tiktoken.get_encoding(name)


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
