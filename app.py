from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import AppConfig, apply_config_to_env, configure_logging, load_config
from config import prefetch_tiktoken_encodings
from utils.vectorstore import _get_vectorstore
from router.api import router as api_router


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="open-deepwiki", version="0.1.0")

    # CORS middleware must be added before the application starts.
    # Starlette raises if you call `add_middleware()` during the startup event.
    try:
        load_dotenv(override=False)
        config_path = os.getenv("OPEN_DEEPWIKI_CONFIG")
        config: AppConfig = load_config(config_path)
        if bool(getattr(config, "cors_enabled", False)):
            fastapi_app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                allow_credentials=False,
            )
    except Exception:
        # If config can't be loaded at import time, we keep the app bootable.
        # Startup will surface the real configuration error.
        pass

    fastapi_app.include_router(api_router, prefix="/api/v1")

    @fastapi_app.on_event("startup")
    def _startup() -> None:
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
