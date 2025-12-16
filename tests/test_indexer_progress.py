from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from indexer import scan_java_methods


class _ParserStub:
    def parse_java_file(self, java_code: str, *, file_path: Optional[str] = None):  # type: ignore[no-untyped-def]
        return []


def test_scan_java_methods_reports_progress_counts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src" / "main" / "java"
        src.mkdir(parents=True)

        (src / "A.java").write_text("class A {}\n", encoding="utf-8")
        (src / "B.java").write_text("class B {}\n", encoding="utf-8")

        events: List[Tuple[int, int, Optional[str]]] = []

        def cb(processed: int, total: int, current: Optional[str]) -> None:
            events.append((processed, total, current))

        methods = scan_java_methods(str(root), _ParserStub(), progress_callback=cb)
        assert methods == []

        # First event should declare total and 0 processed.
        assert events[0][0] == 0
        assert events[0][1] == 2

        # Last event should show all files processed.
        assert events[-1][0] == 2
        assert events[-1][1] == 2
