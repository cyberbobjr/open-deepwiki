from __future__ import annotations

import os
import tempfile
import unittest

from langgraph.checkpoint.base import empty_checkpoint

from utils.sqlite_checkpointer import SqliteCheckpointSaver


class TestSqliteCheckpointSaver(unittest.TestCase):
    def test_put_and_get_tuple_persists_channel_values(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "checkpoints.sqlite3")
            saver = SqliteCheckpointSaver(sqlite_path=db_path)

            config = {"configurable": {"thread_id": "t1", "checkpoint_ns": "proj"}}
            cp = empty_checkpoint()
            cp["channel_values"] = {"x": 123}
            cp["channel_versions"] = {"x": 1}

            new_config = saver.put(config, cp, {"source": "input", "step": -1}, {"x": 1})
            tup = saver.get_tuple(new_config)
            self.assertIsNotNone(tup)
            assert tup is not None
            self.assertEqual(tup.checkpoint["channel_values"].get("x"), 123)

            # New instance should also see it.
            saver2 = SqliteCheckpointSaver(sqlite_path=db_path)
            tup2 = saver2.get_tuple(new_config)
            self.assertIsNotNone(tup2)
            assert tup2 is not None
            self.assertEqual(tup2.checkpoint["channel_values"].get("x"), 123)

    def test_put_writes_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "checkpoints.sqlite3")
            saver = SqliteCheckpointSaver(sqlite_path=db_path)

            config = {"configurable": {"thread_id": "t1", "checkpoint_ns": "proj"}}
            cp = empty_checkpoint()
            cp["channel_values"] = {}
            cp["channel_versions"] = {}

            new_config = saver.put(config, cp, {"source": "input", "step": -1}, {})
            saver.put_writes(new_config, [("note", "hello")], task_id="task-1")

            tup = saver.get_tuple(new_config)
            self.assertIsNotNone(tup)
            assert tup is not None
            self.assertTrue(any(w[0] == "task-1" and w[1] == "note" and w[2] == "hello" for w in (tup.pending_writes or [])))


if __name__ == "__main__":
    unittest.main()
