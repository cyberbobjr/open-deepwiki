from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from config import AppConfig, apply_config_to_env, configure_logging, load_config
from utils.vectorstore import _get_vectorstore, _load_method_docs_map
from core.rag.retriever import GraphEnrichedRetriever
from router.api import QueryRequest, QueryResult, router as api_router


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
            vectorstore = _get_vectorstore()
            method_docs_map = _load_method_docs_map(vectorstore)

            fastapi_app.state.vectorstore = vectorstore
            fastapi_app.state.method_docs_map = method_docs_map
            fastapi_app.state.retriever = GraphEnrichedRetriever(
                vectorstore=vectorstore,
                method_docs_map=method_docs_map,
                k=int(os.getenv("RAG_K", "4")),
            )
        except Exception as e:  # pragma: no cover
            logging.getLogger(__name__).exception("Failed to initialize vectorstore/retriever")
            fastapi_app.state.startup_error = str(e)

    return fastapi_app


app = create_app()
