from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (AppConfig, apply_config_to_env, configure_logging,
                    load_config, prefetch_tiktoken_encodings)
from router.api import router as api_router
from utils.vectorstore import _get_vectorstore


def create_app() -> FastAPI:
    # Load config once for CORS middleware setup before app creation
    load_dotenv(override=False)
    config_path_env = os.getenv("OPEN_DEEPWIKI_CONFIG")
    try:
        early_config: AppConfig = load_config(config_path_env)
    except Exception:
        # If config loading fails (file not found, parse error, etc.),
        # continue without CORS middleware. The app will retry loading
        # during lifespan startup and report errors there if needed.
        early_config = None

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        load_dotenv(override=False)

        config_path = os.getenv("OPEN_DEEPWIKI_CONFIG")
        config: AppConfig = load_config(config_path)
        configure_logging(config.debug_level)

        # Allow specifying LLM/embeddings settings in YAML config.
        apply_config_to_env(config)

        fastapi_app.state.config = config
        fastapi_app.state.config_path = config_path or "open-deepwiki.yaml"
        fastapi_app.state.startup_error = None

        try:
            prefetch_tiktoken_encodings(config)

            vectorstore = _get_vectorstore()
            fastapi_app.state.vectorstore = vectorstore

            # Multi-project server mode: no implicit default project fallback.
            # Caches are populated lazily on the first request per project scope.
            fastapi_app.state.method_docs_maps = {}
            fastapi_app.state.retrievers = {}
            fastapi_app.state.project_overviews = {}
            fastapi_app.state.indexing_statuses = {}
            fastapi_app.state.default_project = None
        except Exception as e:  # pragma: no cover
            logging.getLogger(__name__).exception("Failed to initialize vectorstore/retriever")
            fastapi_app.state.startup_error = str(e)
        
        yield

    fastapi_app = FastAPI(title="open-deepwiki", version="0.1.0", lifespan=lifespan)

    # CORS middleware must be added before the application starts.
    if early_config and bool(getattr(early_config, "cors_enabled", False)):
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )

    fastapi_app.include_router(api_router, prefix="/api/v1")

    return fastapi_app


app = create_app()


def main() -> None:
    load_dotenv(override=False)

    config_path = os.getenv("OPEN_DEEPWIKI_CONFIG")
    config: AppConfig = load_config(config_path)
    configure_logging(config.debug_level)

    # Allow specifying LLM/embeddings settings in YAML config.
    apply_config_to_env(config)

    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=int(config.api_port),
        reload=False,
    )


if __name__ == "__main__":
    main()
