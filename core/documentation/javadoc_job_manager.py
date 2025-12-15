from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory
from core.documentation.postimplementation_log import PostImplementationLog, get_log_dir_from_env


@dataclass
class JavadocJob:
    job_id: str
    root_dir: str
    status: str  # running | completed | failed | stopped
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    stop_requested: bool = False

    # Dedicated log file for this session.
    log_file: Optional[str] = None

    # Results (when completed/stopped)
    summary: Optional[Dict[str, Any]] = None

    # Error (when failed)
    error: Optional[str] = None


def _paths_overlap(a: Path, b: Path) -> bool:
    # Overlap when one is the same as, ancestor of, or descendant of the other.
    if a == b:
        return True
    try:
        if a.is_relative_to(b) or b.is_relative_to(a):
            return True
    except Exception:
        # Defensive: if resolution/relativity fails, do a conservative string-prefix check.
        a_str = str(a)
        b_str = str(b)
        return a_str.startswith(b_str + "/") or b_str.startswith(a_str + "/")

    return False


class JavadocJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, JavadocJob] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._root_paths: Dict[str, Path] = {}
        self._llms: Dict[str, Any] = {}
        self._min_meaningful_lines: Dict[str, int] = {}

    def start(
        self,
        root_dir: str,
        *,
        llm: Optional[Any] = None,
        min_meaningful_lines: int = 3,
    ) -> JavadocJob:
        root_path = Path(root_dir).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            raise ValueError(f"Not a directory: {root_path}")

        with self._lock:
            for existing in self._jobs.values():
                if existing.status != "running":
                    continue
                existing_root = self._root_paths.get(existing.job_id)
                if existing_root is None:
                    continue
                if _paths_overlap(root_path, existing_root):
                    raise RuntimeError(
                        f"A JavaDoc generation is already running for '{existing.root_dir}' "
                        f"(requested: '{root_path}')"
                    )

            job_id = uuid.uuid4().hex
            log = PostImplementationLog.create(get_log_dir_from_env(), session_id=job_id)
            log.write_header(str(root_path), session_id=job_id)
            job = JavadocJob(
                job_id=job_id,
                root_dir=str(root_path),
                status="running",
                created_at=time.time(),
                started_at=time.time(),
                log_file=str(log.path),
            )
            stop_event = threading.Event()

            self._jobs[job_id] = job
            self._stop_events[job_id] = stop_event
            self._root_paths[job_id] = root_path
            self._llms[job_id] = llm
            self._min_meaningful_lines[job_id] = int(min_meaningful_lines)

            thread = threading.Thread(
                target=self._run_job,
                name=f"javadoc-job-{job_id}",
                args=(job_id,),
                daemon=True,
            )
            self._threads[job_id] = thread
            thread.start()

            return job

    def list(self) -> List[JavadocJob]:
        with self._lock:
            # Newest first
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def stop(self, job_id: str) -> JavadocJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status != "running":
                return job

            job.stop_requested = True
            ev = self._stop_events.get(job_id)
            if ev is not None:
                ev.set()
            return job

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            stop_event = self._stop_events.get(job_id)
            llm = self._llms.get(job_id)
            min_meaningful_lines = self._min_meaningful_lines.get(job_id, 3)

        if job is None or stop_event is None:
            return

        try:
            summary = generate_missing_javadoc_in_directory(
                job.root_dir,
                log_dir=get_log_dir_from_env(),
                log=PostImplementationLog(path=Path(job.log_file)) if job.log_file else None,
                session_id=job.job_id,
                llm=llm,
                stop_event=stop_event,
                min_meaningful_lines=int(min_meaningful_lines),
            )
            with self._lock:
                job.summary = summary
                job.finished_at = time.time()
                job.status = "stopped" if job.stop_requested or stop_event.is_set() else "completed"
        except Exception as e:
            with self._lock:
                job.error = str(e)
                job.finished_at = time.time()
                job.status = "failed"


# In-memory singleton (per process)
JAVADOC_JOB_MANAGER = JavadocJobManager()
