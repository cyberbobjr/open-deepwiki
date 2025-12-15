from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class PostImplementationLog:
    path: Path

    @staticmethod
    def create(log_dir: str, *, session_id: Optional[str] = None) -> "PostImplementationLog":
        directory = Path(log_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)

        # Unique per "session" (generation run). Include microseconds + random suffix to
        # avoid collisions when multiple runs start within the same second.
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
        suffix = str(session_id) if session_id else uuid.uuid4().hex[:8]
        filename = f"postimplementation_{ts}_{suffix}.log"
        path = directory / filename
        path.touch(exist_ok=True)
        return PostImplementationLog(path=path)

    def write_header(self, root_dir: str, *, session_id: Optional[str] = None) -> None:
        self.append_line(f"# postimplementation log")
        self.append_line(f"# created_utc={datetime.now(timezone.utc).isoformat()}")
        self.append_line(f"# root_dir={root_dir}")
        if session_id:
            self.append_line(f"# session_id={session_id}")

    def append_change(
        self,
        *,
        file_path: str,
        signature: str,
        member_type: str,
        reason: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.append_line(
            f"{now}\tUPDATED_JAVADOC\tfile={file_path}\ttype={member_type}\tsignature={signature}\treason={reason}"
        )

    def append_line(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + os.linesep)


def get_log_dir_from_env(default: str = "./postimplementation_logs") -> str:
    return os.getenv("POSTIMPLEMENTATION_LOG_DIR", default)


def safe_log_filename(name: str) -> Optional[str]:
    """Validate a log filename from user input.

    Allows only simple filenames and blocks path traversal.
    """

    if not name or name in {".", ".."}:
        return None
    if "/" in name or "\\" in name:
        return None
    return name
