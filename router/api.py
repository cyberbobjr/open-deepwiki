"""API router aggregator.

This module exists only to keep the public import stable:

    `from router.api import router`

All endpoint implementations live in dedicated `router/routes_*.py` modules.
"""

from __future__ import annotations

from fastapi import APIRouter

from router.routes_ask import router as ask_router
from router.routes_health import router as health_router
from router.routes_indexing import router as indexing_router
from router.routes_javadoc import router as javadoc_router
from router.routes_logs import router as logs_router
from router.routes_projects import router as projects_router
from router.routes_query import router as query_router


router = APIRouter()
router.include_router(health_router, tags=["Health"])
router.include_router(projects_router, tags=["Projects"])
router.include_router(query_router, tags=["Query"])
router.include_router(ask_router, tags=["Ask"])
router.include_router(indexing_router, tags=["Indexing"])
router.include_router(javadoc_router, tags=["JavaDoc"])
router.include_router(logs_router, tags=["Logs"])
