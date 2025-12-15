from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def create_codebase_agent(
    *,
    root_dir: str,
    retriever: Any,
    checkpointer: Any,
    project_graph_sqlite_path: str = "./project_graph.sqlite3",
    default_project: Optional[str] = None,
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
    from core.project_graph import SqliteProjectGraphStore

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

    graph_path = str(Path(project_graph_sqlite_path).expanduser().resolve())

    @tool("project_graph_overview")
    def project_graph_overview(project: str = "", limit: int = 25) -> str:
        """Return a compact overview of the indexed project graph.

        Args:
            project: Project scope (empty means default/unscoped).
            limit: Max list sizes for top nodes/edges.
        """

        store = SqliteProjectGraphStore(sqlite_path=graph_path)
        proj = (project or "").strip() or (default_project or None)
        return store.overview_text(project=proj, limit=int(limit))

    @tool("project_graph_neighbors")
    def project_graph_neighbors(project: str = "", node_id: str = "", depth: int = 1, limit: int = 60) -> str:
        """Return call graph neighbors around a node_id.

        Args:
            project: Project scope (empty means default/unscoped).
            node_id: A method scoped id (e.g. '<project>::<method_id>') or method id.
            depth: BFS depth (1-4).
            limit: Max edges.
        """

        store = SqliteProjectGraphStore(sqlite_path=graph_path)
        proj = (project or "").strip() or (default_project or None)
        nid = str(node_id or "").strip()
        if not nid:
            return "ERROR: node_id is required"
        if proj and not nid.startswith(f"{proj}::") and "::" not in nid:
            nid = f"{proj}::{nid}"
        return store.neighbors_text(project=proj, node_id=nid, depth=int(depth), limit=int(limit))

    tools.append(project_graph_overview)
    tools.append(project_graph_neighbors)

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
