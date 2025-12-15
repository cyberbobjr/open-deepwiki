from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


@dataclass
class SessionState:
    messages: List[BaseMessage]
    updated_at: float


class InMemorySessionStore:
    """In-memory conversation store keyed by (project, session_id).

    This is intentionally ephemeral (process memory). For persistence across restarts,
    back it with Redis/SQLite later.
    """

    def __init__(self, *, max_messages: int = 20):
        self._max_messages = int(max_messages)
        self._sessions: Dict[Tuple[Optional[str], str], SessionState] = {}

    def new_session_id(self) -> str:
        return uuid.uuid4().hex

    def get_messages(self, *, project: Optional[str], session_id: str) -> List[BaseMessage]:
        state = self._sessions.get((project, session_id))
        if not state:
            return []
        return list(state.messages)

    def append_turn(
        self,
        *,
        project: Optional[str],
        session_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        key = (project, session_id)
        state = self._sessions.get(key)
        if not state:
            state = SessionState(messages=[], updated_at=time.time())
            self._sessions[key] = state

        state.messages.append(HumanMessage(content=user_text))
        state.messages.append(AIMessage(content=assistant_text))

        if self._max_messages > 0 and len(state.messages) > self._max_messages:
            state.messages = state.messages[-self._max_messages :]

        state.updated_at = time.time()


class SqliteSessionStore:
    """SQLite-backed conversation store keyed by (project, session_id).

    This persists history across process restarts.
    """

    def __init__(self, *, sqlite_path: str, max_messages: int = 20):
        import sqlite3

        self._max_messages = int(max_messages)
        self._path = str(Path(sqlite_path).expanduser().resolve())

        Path(self._path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_messages_lookup ON session_messages(project, session_id, id)"
            )

    def new_session_id(self) -> str:
        return uuid.uuid4().hex

    def get_messages(self, *, project: Optional[str], session_id: str) -> List[BaseMessage]:
        import sqlite3

        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM session_messages
                WHERE (project IS ? OR project = ?) AND session_id = ?
                ORDER BY id ASC
                """,
                (project, project, session_id),
            ).fetchall()

        out: List[BaseMessage] = []
        for role, content in rows:
            if role == "user":
                out.append(HumanMessage(content=content))
            elif role == "assistant":
                out.append(AIMessage(content=content))
            else:
                # Unknown role; store as AI message to keep continuity.
                out.append(AIMessage(content=content))
        return out

    def append_turn(
        self,
        *,
        project: Optional[str],
        session_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        import sqlite3

        now = float(time.time())
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO session_messages(project, session_id, role, content, created_at)
                VALUES (?, ?, 'user', ?, ?)
                """,
                (project, session_id, user_text, now),
            )
            conn.execute(
                """
                INSERT INTO session_messages(project, session_id, role, content, created_at)
                VALUES (?, ?, 'assistant', ?, ?)
                """,
                (project, session_id, assistant_text, now + 1e-6),
            )

            if self._max_messages > 0:
                # Keep only the most recent N messages for this session.
                conn.execute(
                    """
                    DELETE FROM session_messages
                    WHERE id IN (
                        SELECT id
                        FROM session_messages
                        WHERE (project IS ? OR project = ?) AND session_id = ?
                        ORDER BY id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (project, project, session_id, self._max_messages),
                )
