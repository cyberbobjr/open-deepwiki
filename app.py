from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

from config import AppConfig, apply_config_to_env, configure_logging, load_config
from config import prefetch_tiktoken_encodings
from utils.vectorstore import _get_vectorstore, _load_method_docs_map
from core.rag.retriever import GraphEnrichedRetriever
from router.api import router as api_router


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="open-deepwiki", version="0.1.0")

    fastapi_app.include_router(api_router)

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
            default_project = getattr(config, "project_name", None) or os.getenv("OPEN_DEEPWIKI_PROJECT")
            method_docs_map = _load_method_docs_map(vectorstore, project=default_project)

            fastapi_app.state.vectorstore = vectorstore
            # Scoped caches
            fastapi_app.state.method_docs_maps = {default_project: method_docs_map}
            fastapi_app.state.retrievers = {
                default_project: GraphEnrichedRetriever(
                    vectorstore=vectorstore,
                    method_docs_map=method_docs_map,
                    k=int(os.getenv("RAG_K", "4")),
                    project=default_project,
                )
            }

            # Backward-compatible single retriever/map
            fastapi_app.state.method_docs_map = method_docs_map
            fastapi_app.state.retriever = fastapi_app.state.retrievers[default_project]
            fastapi_app.state.default_project = default_project
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
