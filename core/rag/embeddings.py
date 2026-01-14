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


def _env_int(name: str) -> Optional[int]:
    """Read an environment variable as an integer.

    Args:
        name: Environment variable name.

    Returns:
        Parsed integer value, or None if not set.

    Raises:
        ValueError: If the variable is set but not a valid integer.
    """

    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except Exception as e:
        raise ValueError(f"Invalid integer for {name}: {raw!r}") from e


def _truncate_texts_for_embeddings(
    texts: list[str],
    *,
    max_input_tokens: int,
    token_encoding_name: Optional[str],
    model: str,
) -> list[str]:
    """Truncate embedding inputs to a maximum token count.

    This is a defensive measure for providers that enforce strict input limits.

    Args:
        texts: List of input strings.
        max_input_tokens: Maximum number of tokens allowed for each input string.
        token_encoding_name: Optional explicit tiktoken encoding name.
        model: Embeddings model name used for encoding inference.

    Returns:
        List of strings (same length as input) truncated to <= max_input_tokens.

    Raises:
        RuntimeError: If tiktoken is not installed.
        ValueError: If max_input_tokens is invalid.
    """

    if max_input_tokens <= 0:
        raise ValueError("max_input_tokens must be a positive integer")

    try:
        import tiktoken  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Embedding token limit is enabled but 'tiktoken' is not installed. "
            "Install it (pip install tiktoken) or disable embeddings_max_input_tokens."
        ) from e

    if token_encoding_name:
        enc = tiktoken.get_encoding(token_encoding_name)
    else:
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

    out: list[str] = []
    for text in texts:
        if text is None:
            out.append("")
            continue

        # Fast path: empty/short strings.
        raw = str(text)
        tokens = enc.encode(raw)
        if len(tokens) <= max_input_tokens:
            out.append(raw)
            continue

        truncated = enc.decode(tokens[:max_input_tokens])
        out.append(truncated)

    return out


class TokenLimitedOpenAIEmbeddings(OpenAIEmbeddings):
    """OpenAIEmbeddings wrapper that truncates long inputs by token count.

    The limit is controlled by environment variables:
    - OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS
    - OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        max_tokens = _env_int("OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS")
        if max_tokens is not None:
            texts = _truncate_texts_for_embeddings(
                list(texts),
                max_input_tokens=max_tokens,
                token_encoding_name=os.getenv("OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING"),
                model=str(getattr(self, "model", "")) or os.getenv("OPENAI_EMBEDDING_MODEL", ""),
            )
        return super().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        max_tokens = _env_int("OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS")
        if max_tokens is not None:
            truncated = _truncate_texts_for_embeddings(
                [str(text)],
                max_input_tokens=max_tokens,
                token_encoding_name=os.getenv("OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING"),
                model=str(getattr(self, "model", "")) or os.getenv("OPENAI_EMBEDDING_MODEL", ""),
            )[0]
            text = truncated
        return super().embed_query(text)


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

    # Resolve API Key for Embeddings
    # 1. Specific Env Var
    # 2. General Env Var
    api_key = os.getenv("OPEN_DEEPWIKI_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")

    kwargs: Dict[str, Any] = {
        "model": model,
        "openai_api_key": api_key,
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
            return TokenLimitedOpenAIEmbeddings(**{**kwargs, key: base_url})
        except TypeError:
            continue

    raise TypeError(
        "OpenAIEmbeddings does not accept a base URL parameter (tried: base_url, openai_api_base)."
    )
