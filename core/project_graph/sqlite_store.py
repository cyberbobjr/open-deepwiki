from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.parsing.java_parser import JavaMethod


@dataclass(frozen=True)
class GraphStats:
    project: Optional[str]
    files: int
    methods: int
    call_edges: int
    contains_edges: int


class SqliteProjectGraphStore:
    """SQLite-backed project graph.

    This is meant to capture a persistent "big picture" view of the indexed project.

    Storage model:
    - Nodes: methods + files
    - Edges:
      - file -> method (contains)
      - method -> method (calls)

    Notes:
    - `calls` in JavaMethod is only method names (identifiers). Resolving call edges is
      best-effort by matching call names against method signatures (same heuristic as
      GraphEnrichedRetriever).
    """

    def __init__(self, *, sqlite_path: str):
        self._path = str(Path(sqlite_path).expanduser().resolve())
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    project TEXT NULL,
                    node_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    file_path TEXT NULL,
                    signature TEXT NULL,
                    PRIMARY KEY(project, node_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    project TEXT NULL,
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    type TEXT NOT NULL,
                    PRIMARY KEY(project, src, dst, type)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(project, src)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(project, dst)")

    @staticmethod
    def _scoped_id(project: Optional[str], method_id: str) -> str:
        return f"{project}::{method_id}" if project else method_id

    @staticmethod
    def _file_node_id(project: Optional[str], file_path: str) -> str:
        return f"{project}::file::{file_path}" if project else f"file::{file_path}"

    def rebuild(self, *, project: Optional[str], methods: Sequence[JavaMethod]) -> GraphStats:
        """Rebuild graph for a project scope from a set of parsed methods."""

        project_key = project

        # Clear existing.
        with sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM edges WHERE project IS ? OR project = ?", (project_key, project_key))
            conn.execute("DELETE FROM nodes WHERE project IS ? OR project = ?", (project_key, project_key))

        method_nodes: List[Tuple[Optional[str], str, str, str, Optional[str], Optional[str]]] = []
        file_nodes: Dict[str, Tuple[Optional[str], str, str, str, str, Optional[str]]] = {}

        contains_edges: List[Tuple[Optional[str], str, str, str]] = []
        call_edges: List[Tuple[Optional[str], str, str, str]] = []

        # Precompute signature match index.
        method_index: List[Tuple[str, str]] = []  # (node_id, signature_lower)

        for m in methods:
            fp = getattr(m, "file_path", None) or "(unknown)"
            node_id = self._scoped_id(project_key, m.id)
            label = m.signature or m.id

            method_nodes.append((project_key, node_id, "method", label, fp, m.signature))
            method_index.append((node_id, (m.signature or "").lower()))

            file_node_id = self._file_node_id(project_key, fp)
            if file_node_id not in file_nodes:
                file_nodes[file_node_id] = (project_key, file_node_id, "file", fp, fp, None)

            contains_edges.append((project_key, file_node_id, node_id, "contains"))

        # Build call edges (best-effort).
        for m in methods:
            src = self._scoped_id(project_key, m.id)
            calls = list(getattr(m, "calls", None) or [])
            for call_name in calls:
                cn = str(call_name).strip().lower()
                if not cn:
                    continue
                for dst, sig_lower in method_index:
                    if cn in sig_lower:
                        if dst != src:
                            call_edges.append((project_key, src, dst, "calls"))

        # Deduplicate in Python before insert.
        call_edges = list(dict.fromkeys(call_edges))
        contains_edges = list(dict.fromkeys(contains_edges))

        with sqlite3.connect(self._path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO nodes(project, node_id, kind, label, file_path, signature) VALUES (?, ?, ?, ?, ?, ?)",
                list(file_nodes.values()) + method_nodes,
            )
            conn.executemany(
                "INSERT OR REPLACE INTO edges(project, src, dst, type) VALUES (?, ?, ?, ?)",
                contains_edges + call_edges,
            )

        file_count = len({getattr(m, "file_path", None) or "(unknown)" for m in methods})
        return GraphStats(
            project=project_key,
            files=file_count,
            methods=len(method_nodes),
            call_edges=len(call_edges),
            contains_edges=len(contains_edges),
        )

    def overview_text(self, *, project: Optional[str], limit: int = 25) -> str:
        """Return a compact project overview from stored nodes/edges."""

        project_key = project

        with sqlite3.connect(self._path) as conn:
            method_count = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE (project IS ? OR project = ?) AND kind='method'",
                (project_key, project_key),
            ).fetchone()[0]
            file_count = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE (project IS ? OR project = ?) AND kind='file'",
                (project_key, project_key),
            ).fetchone()[0]
            call_edges = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE (project IS ? OR project = ?) AND type='calls'",
                (project_key, project_key),
            ).fetchone()[0]

            top_callers = conn.execute(
                """
                SELECT src, COUNT(*) AS c
                FROM edges
                WHERE (project IS ? OR project = ?) AND type='calls'
                GROUP BY src
                ORDER BY c DESC
                LIMIT ?
                """,
                (project_key, project_key, int(max(1, limit))),
            ).fetchall()

            top_callees = conn.execute(
                """
                SELECT dst, COUNT(*) AS c
                FROM edges
                WHERE (project IS ? OR project = ?) AND type='calls'
                GROUP BY dst
                ORDER BY c DESC
                LIMIT ?
                """,
                (project_key, project_key, int(max(1, limit))),
            ).fetchall()

            sample_edges = conn.execute(
                """
                SELECT src, dst
                FROM edges
                WHERE (project IS ? OR project = ?) AND type='calls'
                ORDER BY src, dst
                LIMIT ?
                """,
                (project_key, project_key, int(max(1, limit))),
            ).fetchall()

            labels = self._labels_for_nodes(conn, project_key, [r[0] for r in top_callers + top_callees])

        proj_line = f"Project: {project_key}" if project_key else "Project: (default)"
        lines: List[str] = [proj_line]
        lines.append(f"Files indexed: {int(file_count)}")
        lines.append(f"Methods indexed: {int(method_count)}")
        lines.append(f"Call edges (best-effort): {int(call_edges)}")

        if top_callers:
            lines.append("\nTop callers (out-degree):")
            for node_id, c in top_callers[:limit]:
                label = labels.get(node_id) or node_id
                lines.append(f"- {label} (calls={int(c)})")

        if top_callees:
            lines.append("\nTop callees (in-degree):")
            for node_id, c in top_callees[:limit]:
                label = labels.get(node_id) or node_id
                lines.append(f"- {label} (called_by={int(c)})")

        if sample_edges:
            lines.append("\nSample call edges:")
            for src, dst in sample_edges[:limit]:
                lines.append(f"- {labels.get(src, src)} -> {labels.get(dst, dst)}")

        return "\n".join(lines).strip()

    def neighbors_text(
        self,
        *,
        project: Optional[str],
        node_id: str,
        depth: int = 1,
        limit: int = 60,
    ) -> str:
        """Return neighbors (calls/called-by) around a node."""

        project_key = project
        node = str(node_id)
        d = max(1, min(int(depth), 4))
        lim = max(1, min(int(limit), 200))

        frontier = {node}
        visited = {node}
        edges_out: List[Tuple[str, str]] = []
        edges_in: List[Tuple[str, str]] = []

        with sqlite3.connect(self._path) as conn:
            for _ in range(d):
                if not frontier:
                    break
                next_frontier = set()
                for n in list(frontier)[:lim]:
                    out_rows = conn.execute(
                        """
                        SELECT dst FROM edges
                        WHERE (project IS ? OR project = ?) AND type='calls' AND src = ?
                        LIMIT ?
                        """,
                        (project_key, project_key, n, lim),
                    ).fetchall()
                    for (dst,) in out_rows:
                        edges_out.append((n, dst))
                        if dst not in visited:
                            visited.add(dst)
                            next_frontier.add(dst)

                    in_rows = conn.execute(
                        """
                        SELECT src FROM edges
                        WHERE (project IS ? OR project = ?) AND type='calls' AND dst = ?
                        LIMIT ?
                        """,
                        (project_key, project_key, n, lim),
                    ).fetchall()
                    for (src,) in in_rows:
                        edges_in.append((src, n))
                        if src not in visited:
                            visited.add(src)
                            next_frontier.add(src)

                frontier = next_frontier

            labels = self._labels_for_nodes(conn, project_key, list(visited))

        header = labels.get(node, node)
        lines = [f"Node: {header}", f"Depth: {d}"]

        if edges_out:
            lines.append("\nCalls:")
            for src, dst in edges_out[:lim]:
                lines.append(f"- {labels.get(src, src)} -> {labels.get(dst, dst)}")

        if edges_in:
            lines.append("\nCalled by:")
            for src, dst in edges_in[:lim]:
                lines.append(f"- {labels.get(src, src)} -> {labels.get(dst, dst)}")

        return "\n".join(lines).strip()

    def _labels_for_nodes(
        self,
        conn: sqlite3.Connection,
        project: Optional[str],
        node_ids: Iterable[str],
    ) -> Dict[str, str]:
        ids = list(dict.fromkeys([str(n) for n in node_ids if n]))
        if not ids:
            return {}

        # Chunk to avoid SQLite parameter limits.
        out: Dict[str, str] = {}
        chunk_size = 500
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            qmarks = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"""
                SELECT node_id, label
                FROM nodes
                WHERE (project IS ? OR project = ?) AND node_id IN ({qmarks})
                """,
                (project, project, *chunk),
            ).fetchall()
            for node_id, label in rows:
                out[str(node_id)] = str(label)
        return out
