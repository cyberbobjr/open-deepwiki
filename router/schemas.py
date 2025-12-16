from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Query request payload for similarity search."""

    query: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)
    project: str = Field(
        ...,
        min_length=1,
        description=(
            "Project scope name (required). Retrieval is restricted to documents indexed with the same project."
        ),
    )


class QueryResult(BaseModel):
    """Normalized retrieval result used by query/ask endpoints."""

    id: Optional[str] = None
    signature: Optional[str] = None
    type: Optional[str] = None
    calls: Any = None
    has_javadoc: Optional[bool] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    is_dependency: bool = False
    called_from: Optional[str] = None
    page_content: str


class IndexDirectoryRequest(BaseModel):
    """Index-directory request payload."""

    path: str = Field(..., min_length=1, description="Chemin du répertoire à indexer (scan récursif des .java).")
    project: str = Field(
        ...,
        min_length=1,
        description="Project scope name (required) attached to indexed docs.",
    )
    reindex: bool = Field(
        default=False,
        description="If true, deletes existing docs in this scope before indexing.",
    )
    include_file_summaries: Optional[bool] = Field(
        default=None,
        description=(
            "If true, indexes one summary document per Java file (heuristic, no LLM). "
            "Defaults to config.index_file_summaries."
        ),
    )


class IndexDirectoryResponse(BaseModel):
    """Index-directory response payload."""

    path: str
    project: str
    indexed_methods: int
    indexed_file_summaries: int = 0
    loaded_method_docs: int
    indexed_at: Optional[str] = None
    status: str = Field(
        default="done",
        description='Indexing status for this project scope: "in_progress" or "done".',
    )


class IndexingStatusResponse(BaseModel):
    """Indexing status payload for a project scope.

    This is intended for UI polling while a background indexing job runs.
    """

    project: str
    status: str = Field(
        ...,
        description='Indexing status for this project scope: "in_progress" or "done".',
    )
    started_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the current/last job started (if known).",
    )
    finished_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the current/last job finished (if known).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the last run failed (status is still 'done').",
    )

    total_files: Optional[int] = Field(
        default=None,
        description="Total number of Java files to scan for the current/last run (if known).",
    )
    processed_files: Optional[int] = Field(
        default=None,
        description="Number of Java files already processed for the current run (if known).",
    )
    remaining_files: Optional[int] = Field(
        default=None,
        description="Number of Java files remaining for the current run (if known).",
    )
    current_file: Optional[str] = Field(
        default=None,
        description="Best-effort path of the file most recently processed (or being processed).",
    )


class ProjectOverviewResponse(BaseModel):
    """Return the latest stored project overview for a scope."""

    project: str
    overview: str
    indexed_path: Optional[str] = None
    indexed_at: Optional[str] = None


class ProjectDocsIndexResponse(BaseModel):
    """Return the generated docs `index.md` for a project scope.

    This is the landing page of the generated docs site under:
    `<docs_output_dir>/<project>/docs/index.md`.
    """

    project: str
    markdown: str
    updated_at: Optional[str] = None


class ProjectInfo(BaseModel):
    """Project listing entry with last indexing metadata."""

    project: str
    indexed_path: Optional[str] = None
    indexed_at: Optional[str] = None


class ProjectOverviewRequest(BaseModel):
    """Request payload for fetching a project overview.

    Attributes:
        project: Project scope name (required).
    """

    project: str = Field(..., min_length=1, description="Project scope name (required).")


class DeleteProjectRequest(BaseModel):
    """Request payload for deleting a project scope.

    Attributes:
        project: Project scope name (required).
    """

    project: str = Field(..., min_length=1, description="Project scope name (required).")


class DeleteProjectResponse(BaseModel):
    """Response payload for deleting a project scope."""

    project: str
    deleted: bool
    deleted_vectorstore_docs: bool = False
    deleted_graph: bool = False
    deleted_sessions: int = 0
    deleted_output_dir: bool = False


class AskRequest(BaseModel):
    """Ask request payload for LLM + RAG."""

    question: str = Field(..., min_length=1)
    k: int = Field(4, ge=1, le=50)
    project: str = Field(
        ...,
        min_length=1,
        description=(
            "Project scope name (required). Retrieval is restricted to documents indexed with the same project."
        ),
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Conversation session id. If omitted, a new session id is created and returned."
        ),
    )


class AskResponse(BaseModel):
    """Ask response payload."""

    session_id: str
    project: str
    answer: str
    context: List[QueryResult]


class DeleteConversationResponse(BaseModel):
    """Response payload for deleting a conversation history."""

    project: str
    session_id: str
    deleted: bool


class DeleteConversationRequest(BaseModel):
    """Request payload for deleting a conversation history.

    Attributes:
        project: Project scope name (required).
        session_id: Conversation session id (required).
    """

    project: str = Field(..., min_length=1, description="Project scope name (required).")
    session_id: str = Field(..., min_length=1, description="Conversation session id to delete.")


class ListConversationsResponse(BaseModel):
    """List conversation sessions for a project."""

    project: str
    sessions: List[str]


class ListConversationsRequest(BaseModel):
    """Request payload for listing conversation sessions.

    Attributes:
        project: Project scope name (required).
    """

    project: str = Field(..., min_length=1, description="Project scope name (required).")


class GenerateJavadocRequest(BaseModel):
    """Start a JavaDoc generation job."""

    path: str = Field(..., min_length=1, description="Chemin du répertoire à scanner (récursif).")


class GenerateJavadocResponse(BaseModel):
    """(Legacy) JavaDoc generation response payload."""

    root_dir: str
    files_scanned: int
    files_modified: int
    members_documented: int
    log_file: str


class GenerateJavadocJobResponse(BaseModel):
    """Response payload for starting a JavaDoc generation job."""

    job_id: str
    root_dir: str
    status: str


class JavadocJobInfo(BaseModel):
    """Status information for a JavaDoc generation job."""

    job_id: str
    root_dir: str
    status: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    stop_requested: bool
    log_file: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class JavadocSessionLogResponse(BaseModel):
    """Return the log contents for a JavaDoc generation job/session."""

    session_id: str
    filename: str
    content: str


class PostImplementationLogInfo(BaseModel):
    """Metadata for a postimplementation log file."""

    filename: str
    size_bytes: int
    modified_at: float


class PostImplementationLogListResponse(BaseModel):
    """List postimplementation logs."""

    log_dir: str
    logs: List[PostImplementationLogInfo]


class PostImplementationLogReadResponse(BaseModel):
    """Read postimplementation log content."""

    filename: str
    content: str
