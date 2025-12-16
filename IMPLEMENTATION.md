# Implementation Summary

This document summarizes the current open-deepwiki implementation (backend + UI) and the main data flows.

## Entrypoints

- `app.py`: FastAPI application factory + `./venv/bin/python app.py` runner
- `indexer.py`: CLI indexer for batch indexing (and optional docs generation)
- `config.py`: YAML config loader + strict environment mapping

## High-level architecture

1. **Index** a Java directory into a named **project** scope
2. **Persist** embeddings + metadata into Chroma (`CHROMA_PERSIST_DIR`, default `./chroma_db`)
3. **Retrieve** using similarity search + dependency enrichment (`calls`)
4. **Answer** via an agent with optional persisted conversation state (SQLite checkpointer)

## Runtime state and persistence

- **Chroma**: persistent vectorstore (`CHROMA_PERSIST_DIR`, `CHROMA_COLLECTION`)
- **Project graph**: SQLite store for call graph + overview (`project_graph_sqlite_path`)
- **Chat sessions**: SQLite checkpointer (`checkpointer_sqlite_path`)
- **Generated docs**: written under `docs_output_dir/<project>/docs/` (default `OUTPUT/<project>/docs/`)
- **Postimplementation logs**: served via `/api/v1/postimplementation-logs` (directory controlled by env)

## Backend API layout

The API router is mounted under the `/api/v1` prefix in `app.py`.

- Router aggregation: `router/api.py`
- Endpoints live in `router/routes_*.py` modules

Key endpoints:

- `/health`: configuration + startup diagnostics
- `/index-directory` + `/index-status`: async indexing job control and polling
- `/projects`, `/projects/details`, `DELETE /projects`: project discovery + lifecycle
- `/query`: similarity search (GraphEnrichedRetriever)
- `/ask` and `/ask/stream`: chat endpoints (SSE streaming supported)
- `/sessions` and `/sessions/delete`: session listing + deletion (SQLite-backed)
- `/project-overview`, `/project-docs-index`, `/projects/{project}/docs/{doc_path}`: generated docs serving

## Indexing pipeline (HTTP)

`POST /api/v1/index-directory` starts indexing in a background thread and returns immediately with `status="in_progress"`.

Implementation notes:

- A process-local `_INDEXING_LOCK` in `router/routes_indexing.py` serializes indexing work to avoid concurrent writes to shared resources.
- Indexing builds the Java tree-sitter grammar if needed (`core/parsing/tree_sitter_setup.py`).
- Parsed methods are indexed via `core/rag/indexing.py`.
- If enabled, file summary documents are indexed to help file-level retrieval.
- A SQLite-backed project graph is rebuilt per project (`core/project_graph/sqlite_store.py`).
- Best-effort docs generation runs during indexing (project overview + feature docs under `OUTPUT/<project>/docs/`).

## Retrieval + chat

- `core/rag/retriever.py` implements `GraphEnrichedRetriever`:
   - similarity search (primary hits)
   - enrich results by following `calls`
- `router/routes_ask.py` wraps retrieval into:
   - a non-streaming `POST /ask` response
   - a streaming `POST /ask/stream` SSE endpoint

Conversation state can be persisted via the SQLite checkpointer.

## Strict LLM configuration

The project intentionally avoids silent fallbacks:

- Embeddings require an explicit base URL + model (`OPENAI_EMBEDDING_API_BASE`, `OPENAI_EMBEDDING_MODEL`).
- Chat requires an explicit base URL + model (`OPENAI_CHAT_API_BASE`, `OPENAI_CHAT_MODEL`).

These can come from environment variables or from YAML config (mapped into env by `config.apply_config_to_env`).

## Front-end

The UI lives under `front/` (Vite + Vue + Pinia) and talks to the backend via `/api/v1/*`.

Notable UI behavior:

- When a project indexing job starts, the projects grid shows a disabled card with a spinner until `/index-status` reports `done`.
