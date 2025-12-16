from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage

from core.rag.retriever import GraphEnrichedRetriever
from router.common import get_scoped_retriever, normalize_project
from router.schemas import (
    AskRequest,
    AskResponse,
    DeleteConversationResponse,
    DeleteConversationRequest,
    ConversationHistoryMessage,
    GetConversationHistoryRequest,
    GetConversationHistoryResponse,
    ListConversationsResponse,
    ListConversationsRequest,
    QueryResult,
)


router = APIRouter()


def _stringify_message_content(content: Any) -> str:
    """Convert a LangChain message content value to a displayable string.

    Args:
        content: Message content value. May be a string or structured content.

    Returns:
        A string representation suitable for JSON transport.
    """

    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def _message_role_and_content(message: Any) -> tuple[str, str]:
    """Normalize a LangChain/LangGraph message to a simple role/content tuple.

    Args:
        message: A LangChain message object or a serialized dict-like message.

    Returns:
        (role, content) where role is one of: user/assistant/system/tool/unknown.
    """

    try:
        from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

        if isinstance(message, HumanMessage):
            return ("user", _stringify_message_content(getattr(message, "content", "")))
        if isinstance(message, AIMessage):
            return ("assistant", _stringify_message_content(getattr(message, "content", "")))
        if isinstance(message, SystemMessage):
            return ("system", _stringify_message_content(getattr(message, "content", "")))
        if isinstance(message, BaseMessage):
            msg_type = str(getattr(message, "type", "") or "unknown").lower()
            role_map = {
                "human": "user",
                "ai": "assistant",
                "system": "system",
                "tool": "tool",
            }
            role = role_map.get(msg_type, msg_type or "unknown")
            return (role, _stringify_message_content(getattr(message, "content", "")))
    except Exception:
        # Best-effort fallback if langchain types are unavailable.
        pass

    if isinstance(message, dict):
        role_raw = (
            message.get("role")
            or message.get("type")
            or message.get("message_type")
            or "unknown"
        )
        role = str(role_raw).lower().strip() or "unknown"
        role_map = {
            "human": "user",
            "ai": "assistant",
        }
        role = role_map.get(role, role)
        return (role, _stringify_message_content(message.get("content")))

    return ("unknown", _stringify_message_content(getattr(message, "content", message)))


def _extract_history_messages(channel_values: dict[str, Any]) -> list[Any]:
    """Extract the conversation history messages list from checkpoint channel values.

    Args:
        channel_values: The `checkpoint['channel_values']` mapping from a LangGraph checkpoint.

    Returns:
        A list of message objects (often LangChain BaseMessage instances). Returns an empty
        list if no suitable messages list is found.
    """

    # Most common key for agent graphs that use a message state.
    primary = channel_values.get("messages")
    if isinstance(primary, list):
        return primary

    for key in ("chat_history", "history", "conversation"):
        val = channel_values.get(key)
        if isinstance(val, list):
            return val

    # Fallback: scan for a list that looks like messages.
    try:
        from langchain_core.messages import BaseMessage

        for val in channel_values.values():
            if isinstance(val, list) and any(isinstance(x, BaseMessage) for x in val):
                return val
    except Exception:
        pass

    return []


@router.post("/ask/stream")
async def ask_stream(request: Request, req: AskRequest) -> StreamingResponse:
    """Ask and stream the assistant response via SSE.

    Args:
        request: FastAPI request.
        req: Ask request payload. `project` is provided in the JSON body.

    Returns:
        StreamingResponse using `text/event-stream`.
    """

    async def _stream() -> AsyncIterator[str]:
        import asyncio
        import json
        from threading import Thread

        def _sse(event: str, data: Any) -> str:
            return f"event: {event}\n" + f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        if getattr(request.app.state, "startup_error", None):
            yield _sse(
                "error",
                {"message": f"Startup failed: {request.app.state.startup_error}"},
            )
            return
        if not os.getenv("OPENAI_API_KEY"):
            yield _sse(
                "error",
                {"message": "OPENAI_API_KEY is not set; cannot run chat completion."},
            )
            return

        normalized_project = normalize_project(req.project)
        retriever : GraphEnrichedRetriever = get_scoped_retriever(request, project=normalized_project)
        retriever.k = req.k

        docs = retriever.get_relevant_documents(req.question)

        project_overviews = getattr(request.app.state, "project_overviews", None) or {}
        project_overview_entry = project_overviews.get(normalized_project)
        project_overview: Any = None
        if isinstance(project_overview_entry, str):
            project_overview = project_overview_entry
        elif isinstance(project_overview_entry, dict):
            project_overview = project_overview_entry.get("overview")

        context_results: List[QueryResult] = []
        context_blocks: List[str] = []

        if isinstance(project_overview, str) and project_overview.strip():
            context_blocks.append(f"### project_overview\n{project_overview.strip()}")

        for doc in docs:
            meta = doc.metadata or {}
            context_results.append(
                QueryResult(
                    id=meta.get("id"),
                    signature=meta.get("signature"),
                    type=meta.get("type"),
                    calls=meta.get("calls"),
                    has_javadoc=meta.get("has_javadoc"),
                    file_path=meta.get("file_path"),
                    start_line=meta.get("start_line"),
                    end_line=meta.get("end_line"),
                    is_dependency=bool(meta.get("is_dependency", False)),
                    called_from=meta.get("called_from"),
                    page_content=doc.page_content,
                )
            )

            header = []
            if meta.get("signature"):
                header.append(f"signature={meta.get('signature')}")
            if meta.get("id"):
                header.append(f"id={meta.get('id')}")
            if meta.get("is_dependency"):
                header.append("dependency=true")
            if meta.get("called_from"):
                header.append(f"called_from={meta.get('called_from')}")
            header_text = " | ".join(header) if header else "context"
            context_blocks.append(f"### {header_text}\n{doc.page_content}")

        from utils.agent_factory import create_codebase_agent
        from utils.sqlite_checkpointer import SqliteCheckpointSaver
        from utils.chat import create_chat_model

        session_id = req.session_id or uuid.uuid4().hex

        yield _sse("meta", {"session_id": session_id, "project": normalized_project})
        context_payload = []
        for c in context_results:
            if hasattr(c, "model_dump"):
                context_payload.append(c.model_dump())
            else:
                context_payload.append(c.dict())
        yield _sse("context", {"context": context_payload})

        system_prompt = (
            "You are a senior engineer assistant for a Java codebase. "
            "Prefer answering using the provided Context section. "
            "If the context is insufficient, you MAY use tools to inspect the codebase (browse_dir/get_file_contents/vector_search) "
            "to gather missing details. "
            "Conversation history is for continuity only. "
            "If you still cannot answer, say what you need next. "
            "Keep the answer concise and actionable."
        )

        user_prompt = "\n\n".join(
            [
                f"Question:\n{req.question}",
                "Context:",
                "\n\n".join(context_blocks) if context_blocks else "(no context)",
            ]
        )

        config = getattr(request.app.state, "config", None)
        code_root = getattr(config, "java_codebase_dir", "./") or "./"
        code_root_key = str(Path(code_root).expanduser().resolve())

        cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
        if cp_backend != "sqlite":
            yield _sse(
                "error",
                {"message": f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')"},
            )
            return

        cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
        cp_path_key = str(Path(cp_path).expanduser().resolve())

        if not hasattr(request.app.state, "checkpointers"):
            request.app.state.checkpointers = {}
        checkpointers: Dict[str, Any] = request.app.state.checkpointers
        if cp_path_key not in checkpointers:
            checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
        checkpointer = checkpointers[cp_path_key]

        loop = asyncio.get_running_loop()
        token_queue: "asyncio.Queue[Any]" = asyncio.Queue()
        error_holder: Dict[str, str] = {}
        done_holder: Dict[str, str] = {"answer": ""}

        class _QueueTokenHandler(BaseCallbackHandler):
            """Push new LLM tokens into an asyncio queue."""

            def on_llm_new_token(self, token: str, **kwargs: Any) -> None:  # type: ignore[override]
                try:
                    loop.call_soon_threadsafe(token_queue.put_nowait, token)
                except Exception:
                    pass

        handler = _QueueTokenHandler()
        llm = create_chat_model(streaming=True, callbacks=[handler])

        graph_path = str(getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3") or "./project_graph.sqlite3")
        agent = create_codebase_agent(
            root_dir=code_root_key,
            retriever=retriever,
            checkpointer=checkpointer,
            llm=llm,
            project_graph_sqlite_path=graph_path,
            default_project=normalized_project or None,
            debug=(str(getattr(config, "debug_level", "")).upper() == "DEBUG"),
            system_prompt=system_prompt,
        )

        def _run_agent() -> None:
            try:
                agent_result = agent.invoke(
                    {"messages": [HumanMessage(content=user_prompt)]},
                    {
                        "configurable": {
                            "thread_id": session_id,
                            "checkpoint_ns": normalized_project or "",
                        }
                    },
                )

                messages = (
                    (agent_result or {}).get("messages", [])
                    if isinstance(agent_result, dict)
                    else []
                )
                last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
                answer_text = getattr(last_ai, "content", None)
                if not isinstance(answer_text, str) or not answer_text.strip():
                    answer_text = str(last_ai or agent_result)
                done_holder["answer"] = answer_text
            except Exception as e:
                error_holder["message"] = f"Chat request failed: {e}"
            finally:
                try:
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)
                except Exception:
                    pass

        Thread(target=_run_agent, daemon=True).start()

        answer_parts: List[str] = []

        while True:
            if await request.is_disconnected():
                return

            token = await token_queue.get()
            if token is None:
                break
            answer_parts.append(str(token))
            yield _sse("token", {"delta": str(token)})

        if error_holder.get("message"):
            yield _sse("error", {"message": error_holder["message"]})
            return

        final_answer = done_holder.get("answer") or "".join(answer_parts)
        yield _sse("done", {"answer": final_answer})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/sessions", response_model=ListConversationsResponse)
def list_conversation_sessions(request: Request, req: ListConversationsRequest) -> ListConversationsResponse:
    """List existing conversation session ids for a project.

    Args:
        request: FastAPI request.
        req: Request payload containing the project scope.

    Returns:
        Response containing the normalized project name and the list of session ids.

    Raises:
        HTTPException: If startup failed or the checkpointer backend is unsupported.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    normalized_project = normalize_project(req.project)

    from utils.sqlite_checkpointer import SqliteCheckpointSaver

    config = getattr(request.app.state, "config", None)
    cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
    if cp_backend != "sqlite":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')",
        )

    cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
    cp_path_key = str(Path(cp_path).expanduser().resolve())

    if not hasattr(request.app.state, "checkpointers"):
        request.app.state.checkpointers = {}
    checkpointers: Dict[str, Any] = request.app.state.checkpointers
    if cp_path_key not in checkpointers:
        checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
    checkpointer = checkpointers[cp_path_key]

    sessions: List[str] = []
    if hasattr(checkpointer, "list_threads_namespace"):
        sessions = list(checkpointer.list_threads_namespace(checkpoint_ns=normalized_project))

    return ListConversationsResponse(project=normalized_project, sessions=sessions)


@router.post("/sessions/history", response_model=GetConversationHistoryResponse)
def get_conversation_history(request: Request, req: GetConversationHistoryRequest) -> GetConversationHistoryResponse:
    """Fetch the persisted message history for a conversation session.

    This reads the latest checkpoint for (session_id, project) from the configured
    checkpointer backend.

    Args:
        request: FastAPI request.
        req: Request payload containing the project scope and session id.

    Returns:
        Response payload containing the messages for the session.

    Raises:
        HTTPException: If startup failed, the backend is unsupported, or the session does not exist.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    normalized_project = normalize_project(req.project)
    sid = str(req.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    from utils.sqlite_checkpointer import SqliteCheckpointSaver

    config = getattr(request.app.state, "config", None)
    cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
    if cp_backend != "sqlite":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')",
        )

    cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
    cp_path_key = str(Path(cp_path).expanduser().resolve())

    if not hasattr(request.app.state, "checkpointers"):
        request.app.state.checkpointers = {}
    checkpointers: Dict[str, Any] = request.app.state.checkpointers
    if cp_path_key not in checkpointers:
        checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
    checkpointer = checkpointers[cp_path_key]

    tup = None
    if hasattr(checkpointer, "get_tuple"):
        tup = checkpointer.get_tuple(
            {
                "configurable": {
                    "thread_id": sid,
                    "checkpoint_ns": normalized_project or "",
                }
            }
        )

    if tup is None:
        raise HTTPException(status_code=404, detail="Session not found")

    checkpoint: Dict[str, Any] = tup.checkpoint if isinstance(tup.checkpoint, dict) else {}
    channel_values: Dict[str, Any] = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}

    raw_messages = _extract_history_messages(channel_values)
    serialized: List[ConversationHistoryMessage] = []
    for m in raw_messages:
        role, content = _message_role_and_content(m)
        if content.strip() or role != "unknown":
            serialized.append(ConversationHistoryMessage(role=role, content=content))

    checkpoint_id: Optional[str] = None
    try:
        cfg = getattr(tup, "config", None) or {}
        conf = cfg.get("configurable", {}) if isinstance(cfg, dict) else {}
        checkpoint_id_val = conf.get("checkpoint_id")
        if checkpoint_id_val is not None:
            checkpoint_id = str(checkpoint_id_val)
    except Exception:
        checkpoint_id = None

    return GetConversationHistoryResponse(
        project=normalized_project,
        session_id=sid,
        checkpoint_id=checkpoint_id,
        messages=serialized,
    )


@router.delete(
    "/sessions/delete",
    response_model=DeleteConversationResponse,
)
def delete_conversation_history(request: Request, req: DeleteConversationRequest) -> DeleteConversationResponse:
    """Delete the persisted conversation history for a session.

    Args:
        request: FastAPI request.
        req: Request payload containing the project scope and session id.

    Returns:
        Response confirming deletion.

    Raises:
        HTTPException: If startup failed, the request is invalid, or the checkpointer backend is unsupported.
    """

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )

    normalized_project = normalize_project(req.project)
    sid = str(req.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    from utils.sqlite_checkpointer import SqliteCheckpointSaver

    config = getattr(request.app.state, "config", None)
    cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
    if cp_backend != "sqlite":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')",
        )

    cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
    cp_path_key = str(Path(cp_path).expanduser().resolve())

    if not hasattr(request.app.state, "checkpointers"):
        request.app.state.checkpointers = {}
    checkpointers: Dict[str, Any] = request.app.state.checkpointers
    if cp_path_key not in checkpointers:
        checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
    checkpointer = checkpointers[cp_path_key]

    if hasattr(checkpointer, "delete_thread_namespace"):
        checkpointer.delete_thread_namespace(thread_id=sid, checkpoint_ns=normalized_project)
    else:  # pragma: no cover
        checkpointer.delete_thread(sid)

    return DeleteConversationResponse(project=normalized_project, session_id=sid, deleted=True)


@router.post("/ask", response_model=AskResponse)
def ask(request: Request, req: AskRequest) -> AskResponse:
    """Ask within a project scope (project provided in request body)."""

    if getattr(request.app.state, "startup_error", None):
        raise HTTPException(
            status_code=503, detail=f"Startup failed: {request.app.state.startup_error}"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set; cannot run chat completion.",
        )

    project = normalize_project(req.project)
    retriever = get_scoped_retriever(request, project=project)
    retriever.k = req.k
    docs = retriever.get_relevant_documents(req.question)

    project_overviews = getattr(request.app.state, "project_overviews", None) or {}
    project_overview_entry = project_overviews.get(project)
    project_overview: Any = None
    if isinstance(project_overview_entry, str):
        project_overview = project_overview_entry
    elif isinstance(project_overview_entry, dict):
        project_overview = project_overview_entry.get("overview")

    context_results: List[QueryResult] = []
    context_blocks: List[str] = []

    if isinstance(project_overview, str) and project_overview.strip():
        context_blocks.append(f"### project_overview\n{project_overview.strip()}")

    for doc in docs:
        meta = doc.metadata or {}
        context_results.append(
            QueryResult(
                id=meta.get("id"),
                signature=meta.get("signature"),
                type=meta.get("type"),
                calls=meta.get("calls"),
                has_javadoc=meta.get("has_javadoc"),
                file_path=meta.get("file_path"),
                start_line=meta.get("start_line"),
                end_line=meta.get("end_line"),
                is_dependency=bool(meta.get("is_dependency", False)),
                called_from=meta.get("called_from"),
                page_content=doc.page_content,
            )
        )

        header = []
        if meta.get("signature"):
            header.append(f"signature={meta.get('signature')}")
        if meta.get("id"):
            header.append(f"id={meta.get('id')}")
        if meta.get("is_dependency"):
            header.append("dependency=true")
        if meta.get("called_from"):
            header.append(f"called_from={meta.get('called_from')}")

        header_text = " | ".join(header) if header else "context"
        context_blocks.append(f"### {header_text}\n{doc.page_content}")

    from utils.agent_factory import create_codebase_agent
    from utils.sqlite_checkpointer import SqliteCheckpointSaver

    system_prompt = (
        "You are a senior engineer assistant for a Java codebase. "
        "Prefer answering using the provided Context section. "
        "If the context is insufficient, you MAY use tools to inspect the codebase (browse_dir/get_file_contents/vector_search) "
        "to gather missing details. "
        "Conversation history is for continuity only. "
        "If you still cannot answer, say what you need next. "
        "Keep the answer concise and actionable."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{req.question}",
            "Context:",
            "\n\n".join(context_blocks) if context_blocks else "(no context)",
        ]
    )

    if not hasattr(request.app.state, "code_agents"):
        request.app.state.code_agents = {}
    if not hasattr(request.app.state, "checkpointers"):
        request.app.state.checkpointers = {}

    session_id = req.session_id or uuid.uuid4().hex

    config = getattr(request.app.state, "config", None)
    code_root = getattr(config, "java_codebase_dir", "./") or "./"
    code_root_key = str(Path(code_root).expanduser().resolve())

    cp_backend = str(getattr(config, "checkpointer_backend", "sqlite") or "sqlite").lower()
    if cp_backend != "sqlite":
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported checkpointer_backend: {cp_backend!r} (supported: 'sqlite')",
        )

    cp_path = str(getattr(config, "checkpointer_sqlite_path", "./checkpoints.sqlite3") or "./checkpoints.sqlite3")
    cp_path_key = str(Path(cp_path).expanduser().resolve())

    checkpointers: Dict[str, Any] = request.app.state.checkpointers
    if cp_path_key not in checkpointers:
        checkpointers[cp_path_key] = SqliteCheckpointSaver(sqlite_path=cp_path_key)
    checkpointer = checkpointers[cp_path_key]

    agents: Dict[str, Any] = request.app.state.code_agents
    agent_key = f"{code_root_key}::{project or ''}"
    if agent_key not in agents:
        graph_path = str(getattr(config, "project_graph_sqlite_path", "./project_graph.sqlite3") or "./project_graph.sqlite3")
        agents[agent_key] = create_codebase_agent(
            root_dir=code_root_key,
            retriever=retriever,
            checkpointer=checkpointer,
            project_graph_sqlite_path=graph_path,
            default_project=project or None,
            debug=(str(getattr(config, "debug_level", "")).upper() == "DEBUG"),
            system_prompt=system_prompt,
        )

    agent = agents[agent_key]

    try:
        agent_result = agent.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": project or "",
                }
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {e}")

    messages = (agent_result or {}).get("messages", []) if isinstance(agent_result, dict) else []
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    answer_text = getattr(last_ai, "content", None)
    if not isinstance(answer_text, str) or not answer_text.strip():
        answer_text = str(last_ai or agent_result)

    return AskResponse(
        session_id=session_id,
        project=project,
        answer=answer_text,
        context=context_results,
    )
