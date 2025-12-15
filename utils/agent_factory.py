from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def create_codebase_agent(
    *,
    root_dir: str,
    retriever: Any,
    checkpointer: Any,
    debug: bool = False,
    system_prompt: Optional[str] = None,
) -> Any:
    """Create a LangChain Agent (graph) with codebase filesystem tools.

    Notes:
    - This creates an *agent* via `langchain.agents.create_agent`.
    - It still needs an underlying chat model (configured via `utils.chat.create_chat_model`).
    """

    from langchain.agents import create_agent
    from langchain_core.tools import tool

    from utils.chat import create_chat_model
    from utils.codebase_tools import make_codebase_tools

    resolved_root = str(Path(root_dir).expanduser().resolve())
    tools = list(make_codebase_tools(root_dir=resolved_root))

    @tool("vector_search")
    def vector_search(query: str, k: int = 4) -> str:
        """Search the indexed codebase (Chroma) and return top matches.

        Args:
            query: Natural language query.
            k: Number of documents to return.

        Returns:
            A compact, human-readable list of results.
        """

        if retriever is None:
            return "ERROR: retriever is not configured"

        try:
            kk = max(1, min(int(k), 50))
        except Exception:
            kk = 4

        old_k = getattr(retriever, "k", None)
        try:
            if old_k is not None:
                setattr(retriever, "k", kk)
            docs = retriever.get_relevant_documents(str(query))
        except Exception as e:
            return f"ERROR: vector search failed: {e}"
        finally:
            if old_k is not None:
                try:
                    setattr(retriever, "k", old_k)
                except Exception:
                    pass

        if not docs:
            return "(no results)"

        blocks = []
        for i, d in enumerate(docs[:kk], start=1):
            meta = getattr(d, "metadata", None) or {}
            sig = meta.get("signature") or meta.get("scoped_id") or meta.get("id") or "(unknown)"
            fp = meta.get("file_path")
            header = f"[{i}] {sig}" + (f" | file={fp}" if fp else "")
            content = getattr(d, "page_content", "") or ""
            if len(content) > 1800:
                content = content[:1800] + "\n… (truncated)"
            blocks.append(header + "\n" + content)

        return "\n\n".join(blocks)

    tools.append(vector_search)

    llm = create_chat_model()

    prompt = system_prompt or (
        "You are a senior engineer assistant for a Java codebase. "
        "You may use tools to inspect the codebase when necessary. "
        "Prefer answering from the provided Context first. "
        "When you read files, cite the relevant snippet in your answer. "
        "Be concise and actionable."
    )

    return create_agent(
        llm,
        tools=tools,
        system_prompt=prompt,
        checkpointer=checkpointer,
        debug=bool(debug),
        name="open-deepwiki-codebase-agent",
    )
