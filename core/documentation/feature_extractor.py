from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from langchain_core.messages import HumanMessage, SystemMessage


@dataclass(frozen=True)
class LLMCallResult:
    """A small wrapper for normalized LLM responses.

    This module supports different LangChain chat model return types by
    normalizing them to a simple string.

    Attributes:
        content: The generated text content.
    """

    content: str


def _truncate_middle(text: str, *, max_chars: int) -> str:
    """Truncate text by keeping the beginning and end.

    Args:
        text: Input text.
        max_chars: Maximum number of characters to return. Must be > 0.

    Returns:
        A possibly-truncated string no longer than `max_chars`.

    Raises:
        ValueError: If `max_chars` is not positive.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    if len(text) <= max_chars:
        return text

    # Keep a larger prefix than suffix; Java files tend to declare package/imports
    # and types at the top, but key business logic often appears later.
    prefix_len = int(max_chars * 0.7)
    suffix_len = max_chars - prefix_len

    prefix = text[:prefix_len].rstrip()
    suffix = text[-suffix_len:].lstrip()

    return (
        prefix
        + "\n\n/* --- TRUNCATED FOR TOKEN LIMITS --- */\n\n"
        + suffix
    )


def _coerce_llm_content(response: Any) -> str:
    """Extract text from common LangChain response shapes."""

    if response is None:
        return ""

    # LangChain AIMessage-like.
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content

    # Some wrappers return dict-like results.
    if isinstance(response, dict):
        val = response.get("content") or response.get("text") or ""
        return str(val) if val is not None else ""

    # Fallback.
    return str(response)


def _invoke_llm(llm: Any, messages: Sequence[Any]) -> LLMCallResult:
    """Invoke a LangChain-compatible chat model.

    Args:
        llm: A LangChain chat model (e.g., ChatOpenAI).
        messages: A list/sequence of System/Human messages.

    Returns:
        Normalized result with `.content`.

    Raises:
        Exception: Propagates model invocation errors.
    """

    # Prefer the modern `.invoke()` API.
    if hasattr(llm, "invoke"):
        response = llm.invoke(list(messages))
        return LLMCallResult(content=_coerce_llm_content(response).strip())

    # Fallback for older call styles.
    response = llm(list(messages))
    return LLMCallResult(content=_coerce_llm_content(response).strip())


def summarize_file_semantically(file_path: Path, code: str, llm: Any) -> str:
    """Generate a semantic file-level summary with an LLM.

    The output is a compact markdown snippet intended to be aggregated into
    module-level and project-level docs.

    Args:
        file_path: Path to the Java file being summarized.
        code: Full Java source code.
        llm: A LangChain chat model instance.

    Returns:
        Markdown string containing:
        - A 2-sentence responsibility summary.
        - A bulleted list of high-level functional features.

    Notes:
        If `code` is empty or the LLM fails, the function returns a best-effort
        fallback markdown section.
    """

    rel_name = str(file_path)
    trimmed = (code or "").strip()
    if not trimmed:
        return f"## {rel_name}\n\n_Empty file._\n"

    # Conservative cap to reduce risk of exceeding context windows across providers.
    # We intentionally use characters to avoid depending on tokenizers.
    max_code_chars = 40_000
    code_for_llm = _truncate_middle(trimmed, max_chars=max_code_chars)

    system = SystemMessage(
        content=(
            "You are a senior software analyst generating DeepWiki-style documentation. "
            "You MUST only use the provided code. If unsure, say you are unsure. "
            "Return clean Markdown. Do not include fenced code blocks."
        )
    )

    human = HumanMessage(
        content=(
            "Analyze this Java source file and produce a concise semantic summary.\n\n"
            "Requirements:\n"
            "1) Start with exactly 2 sentences describing the file's responsibility.\n"
            "2) Then output a section 'Features:' with 3-8 bullet points of business/functional behaviors.\n"
            "   - Avoid purely technical implementation details (e.g., 'uses HashMap').\n"
            "   - Prefer what capabilities it provides (e.g., 'validates invoices', 'sends notifications').\n"
            "3) If the file is mostly glue/DTO/config, say so and list what it configures/represents.\n"
            "4) Keep it short and non-repetitive.\n\n"
            f"File: {rel_name}\n\n"
            "Java code:\n"
            f"{code_for_llm}"
        )
    )

    try:
        result = _invoke_llm(llm, [system, human]).content
        if not result:
            raise RuntimeError("LLM returned empty content")

        # Ensure there is a file header to support hierarchy assembly.
        if not result.lstrip().startswith("##"):
            return f"## {rel_name}\n\n{result.strip()}\n"

        return result.strip() + "\n"
    except Exception as e:
        return (
            f"## {rel_name}\n\n"
            f"_LLM summarization failed: {type(e).__name__}: {e}_\n\n"
            "Features:\n"
            "- (unavailable)\n"
        )


def generate_module_summary(folder_path: Path, file_summaries: List[str], llm: Any) -> str:
    """Generate a module/folder summary by aggregating file-level summaries.

    Args:
        folder_path: Folder path representing the module.
        file_summaries: File-level markdown summaries for Java files inside the folder.
        llm: A LangChain chat model instance.

    Returns:
        A markdown section describing the module capabilities.

    Notes:
        This function truncates the aggregated input to avoid token limits.
        If the LLM fails, it returns a minimal fallback section.
    """

    module_name = str(folder_path)
    summaries = [s.strip() for s in (file_summaries or []) if (s or "").strip()]

    if not summaries:
        return f"## Module: {module_name}\n\n_No Java files found to summarize._\n"

    joined = "\n\n".join(summaries)
    joined = _truncate_middle(joined, max_chars=60_000)

    system = SystemMessage(
        content=(
            "You are generating hierarchical documentation. You will be given file summaries "
            "for a folder. Produce a crisp module description and avoid repeating file names. "
            "Return clean Markdown (no code fences)."
        )
    )

    human = HumanMessage(
        content=(
            "Create a module-level documentation section for this folder.\n\n"
            "Output format:\n"
            "- Start with a 1-2 sentence summary of the module purpose.\n"
            "- Then a 'Capabilities:' bullet list with 4-10 items capturing what the module provides.\n"
            "- Optionally add 'Key Concepts:' with 2-6 bullets if helpful.\n\n"
            f"Folder: {module_name}\n\n"
            "File summaries:\n"
            f"{joined}"
        )
    )

    try:
        result = _invoke_llm(llm, [system, human]).content
        if not result:
            raise RuntimeError("LLM returned empty content")

        if not result.lstrip().startswith("##"):
            return f"## Module: {module_name}\n\n{result.strip()}\n"

        return result.strip() + "\n"
    except Exception as e:
        return (
            f"## Module: {module_name}\n\n"
            f"_LLM module summary failed: {type(e).__name__}: {e}_\n"
        )


def generate_project_overview(root_dir: Path, module_summaries: Dict[str, str], llm: Any) -> str:
    """Generate a DeepWiki-style project overview page.

    Args:
        root_dir: Project root directory being documented.
        module_summaries: Mapping of module identifier -> module summary markdown.
        llm: A LangChain chat model instance.

    Returns:
        A complete markdown page including:
        - Global Overview
        - Key Features
        - Architecture

    Notes:
        This function is designed for human-readable documentation, not for indexing.
        If the LLM fails, returns a minimal fallback page.
    """

    root = str(root_dir)

    items: List[Tuple[str, str]] = sorted(
        ((k, (v or "").strip()) for k, v in (module_summaries or {}).items()),
        key=lambda kv: kv[0],
    )
    if not items:
        return (
            f"# Project Overview\n\n"
            f"Root: `{root}`\n\n"
            "No modules were summarized.\n"
        )

    joined_modules = "\n\n".join(f"### {k}\n\n{v}" for k, v in items if v)
    joined_modules = _truncate_middle(joined_modules, max_chars=90_000)

    system = SystemMessage(
        content=(
            "You are writing a DeepWiki-style documentation page for a software project. "
            "Use only the provided module summaries. Return clean Markdown. "
            "You may include Mermaid diagrams if (and only if) they materially improve understanding. "
            "If you include a diagram, use a fenced Mermaid block: ```mermaid\n...\n```. "
            "Keep diagrams simple. IMPORTANT: "
            "1) Do not use parentheses or brackets in node IDs (e.g., use `id1[Label]` not `id(1)[Label]`). "
            "2) Escape special characters in labels with double quotes. "
            "3) Do not use complex styling."
            "Do not include any other fenced code blocks."
        )
    )

    human = HumanMessage(
        content=(
            "Generate a single markdown page with these exact top-level sections:\n"
            "1) # Project Overview\n"
            "2) ## Global Overview\n"
            "3) ## Key Features (bulleted list)\n"
            "4) ## Architecture (describe module interactions and data flow)\n\n"
            "Guidance:\n"
            "- The Global Overview should be 1 short paragraph.\n"
            "- Key Features should be 6-14 bullets, deduplicated, phrased as user/business outcomes.\n"
            "- Architecture should mention major modules and how they relate (at a high level).\n"
            "- Avoid low-level implementation details.\n\n"
            "Optional (only if it helps):\n"
            "- In the Architecture section, include ONE Mermaid diagram (flowchart/sequence/class) if it clarifies the data flow.\n"
            "- Keep it simple (< 40 lines), no styling, no colors.\n\n"
            f"Project root: {root}\n\n"
            "Module summaries:\n"
            f"{joined_modules}"
        )
    )

    try:
        result = _invoke_llm(llm, [system, human]).content
        if not result:
            raise RuntimeError("LLM returned empty content")

        # Ensure the document begins with the expected title.
        if not result.lstrip().startswith("# Project Overview"):
            return "# Project Overview\n\n" + result.strip() + "\n"

        return result.strip() + "\n"
    except Exception as e:
        return (
            "# Project Overview\n\n"
            f"_LLM project overview failed: {type(e).__name__}: {e}_\n\n"
            "## Global Overview\n\n"
            "(unavailable)\n\n"
            "## Key Features\n\n"
            "- (unavailable)\n\n"
            "## Architecture\n\n"
            "(unavailable)\n"
        )
