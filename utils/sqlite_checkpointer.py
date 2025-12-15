from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence, cast

from langchain_core.runnables import RunnableConfig

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    WRITES_IDX_MAP,
    get_checkpoint_id,
    get_checkpoint_metadata,
)


class SqliteCheckpointSaver(BaseCheckpointSaver[str]):
    """SQLite-backed LangGraph checkpointer.

    Persists checkpoints + channel blobs + pending writes.

    This is a lightweight local backend (single file) intended for dev/self-host.
    """

    def __init__(self, *, sqlite_path: str):
        super().__init__()
        self._path = str(Path(sqlite_path).expanduser().resolve())
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT NULL,
                    checkpoint_type TEXT NOT NULL,
                    checkpoint_blob BLOB NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata_blob BLOB NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_latest ON checkpoints(thread_id, checkpoint_ns, checkpoint_id DESC)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blobs (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    version TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    value_blob BLOB NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    write_idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    value_blob BLOB NOT NULL,
                    task_path TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_writes_lookup ON writes(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)"
            )

    def _load_channel_values(
        self, *, thread_id: str, checkpoint_ns: str, versions: ChannelVersions
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if not versions:
            return values

        with self._connect() as conn:
            for channel, version in versions.items():
                row = conn.execute(
                    """
                    SELECT value_type, value_blob
                    FROM blobs
                    WHERE thread_id=? AND checkpoint_ns=? AND channel=? AND version=?
                    """,
                    (thread_id, checkpoint_ns, channel, str(version)),
                ).fetchone()
                if not row:
                    continue
                v_type, v_blob = row
                if v_type != "empty":
                    values[channel] = self.serde.loads_typed((v_type, v_blob))
        return values

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable = cast(dict[str, Any], config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        if not thread_id:
            raise ValueError("Missing required config: configurable.thread_id")

        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")

        checkpoint_id = get_checkpoint_id(config)

        with self._connect() as conn:
            if checkpoint_id:
                row = conn.execute(
                    """
                    SELECT checkpoint_type, checkpoint_blob, metadata_type, metadata_blob, parent_checkpoint_id
                    FROM checkpoints
                    WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT checkpoint_id, checkpoint_type, checkpoint_blob, metadata_type, metadata_blob, parent_checkpoint_id
                    FROM checkpoints
                    WHERE thread_id=? AND checkpoint_ns=?
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                    """,
                    (thread_id, checkpoint_ns),
                ).fetchone()

        if not row:
            return None

        if checkpoint_id:
            c_type, c_blob, m_type, m_blob, parent_checkpoint_id = row
            effective_config: RunnableConfig = config
            effective_checkpoint_id = checkpoint_id
        else:
            effective_checkpoint_id, c_type, c_blob, m_type, m_blob, parent_checkpoint_id = row
            effective_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": effective_checkpoint_id,
                }
            }

        checkpoint_obj: Checkpoint = self.serde.loads_typed((c_type, c_blob))
        channel_values = self._load_channel_values(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            versions=checkpoint_obj.get("channel_versions", {}),
        )

        # Pending writes
        with self._connect() as conn:
            write_rows = conn.execute(
                """
                SELECT task_id, channel, value_type, value_blob, task_path
                FROM writes
                WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?
                ORDER BY task_id ASC, write_idx ASC
                """,
                (thread_id, checkpoint_ns, effective_checkpoint_id),
            ).fetchall()

        pending_writes = [
            (task_id, channel, self.serde.loads_typed((v_type, v_blob)))
            for (task_id, channel, v_type, v_blob, _task_path) in write_rows
        ]

        metadata = self.serde.loads_typed((m_type, m_blob))

        parent_config = cast(
            Optional[RunnableConfig],
            (
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
                if parent_checkpoint_id
                else None
            ),
        )

        return CheckpointTuple(
            config=effective_config,
            checkpoint={
                **checkpoint_obj,
                "channel_values": channel_values,
            },
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if config is None:
            return iter(())

        configurable = cast(dict[str, Any], config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        if not thread_id:
            return iter(())
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")

        before_id: Optional[str] = None
        if before is not None:
            before_id = get_checkpoint_id(before)

        lim = int(limit) if limit is not None else None

        sql = (
            "SELECT checkpoint_id FROM checkpoints "
            "WHERE thread_id=? AND checkpoint_ns=? "
        )
        params: list[Any] = [thread_id, checkpoint_ns]

        if before_id:
            sql += "AND checkpoint_id < ? "
            params.append(before_id)

        sql += "ORDER BY checkpoint_id DESC"
        if lim is not None:
            sql += " LIMIT ?"
            params.append(lim)

        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        for (checkpoint_id,) in rows:
            tup = self.get_tuple(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                }
            )
            if tup is not None:
                yield tup

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        c = checkpoint.copy()
        configurable = cast(dict[str, Any], config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        if not thread_id:
            raise ValueError("Missing required config: configurable.thread_id")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        parent_checkpoint_id = configurable.get("checkpoint_id")

        values: dict[str, Any] = c.pop("channel_values")  # type: ignore[misc]

        with self._connect() as conn:
            # Store new/updated channel values for the versions written.
            for channel, version in new_versions.items():
                if channel in values:
                    v_type, v_blob = self.serde.dumps_typed(values[channel])
                else:
                    v_type, v_blob = ("empty", b"")

                conn.execute(
                    """
                    INSERT OR REPLACE INTO blobs(thread_id, checkpoint_ns, channel, version, value_type, value_blob)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (thread_id, checkpoint_ns, channel, str(version), v_type, v_blob),
                )

            c_type, c_blob = self.serde.dumps_typed(c)
            m_type, m_blob = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))

            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints(
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                    checkpoint_type, checkpoint_blob, metadata_type, metadata_blob
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint["id"],
                    parent_checkpoint_id,
                    c_type,
                    c_blob,
                    m_type,
                    m_blob,
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = cast(dict[str, Any], config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        if not thread_id:
            raise ValueError("Missing required config: configurable.thread_id")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        checkpoint_id = str(configurable.get("checkpoint_id") or "")
        if not checkpoint_id:
            raise ValueError("Missing required config: configurable.checkpoint_id")

        with self._connect() as conn:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)

                if write_idx >= 0:
                    # Skip if already present.
                    existing = conn.execute(
                        """
                        SELECT 1 FROM writes
                        WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=? AND task_id=? AND write_idx=?
                        """,
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx),
                    ).fetchone()
                    if existing:
                        continue

                v_type, v_blob = self.serde.dumps_typed(value)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO writes(
                        thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx,
                        channel, value_type, value_blob, task_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        int(write_idx),
                        channel,
                        v_type,
                        v_blob,
                        task_path or "",
                    ),
                )

    def delete_thread(self, thread_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM writes WHERE thread_id=?", (thread_id,))
            conn.execute("DELETE FROM blobs WHERE thread_id=?", (thread_id,))
            conn.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
