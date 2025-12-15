"""Backward-compatible import path.

The preferred entrypoint is now the root-level `app.py`.
This module remains to avoid breaking existing imports like:
`uvicorn api.app:app`.
"""

from app import QueryRequest, QueryResult, app, create_app  # noqa: F401
