# Copilot instructions — open-deepwiki (Java Graph RAG API + Indexer)

## Big picture (what we’re building)

- This repo started as a demo in `java_graph_rag.py` (supprimé), but the intended direction est une **vraie application** avec :
  - an **indexing entrypoint** (CLI/job) that parses a Java codebase and writes to a persistent Chroma collection
  - a **query API** (HTTP) that runs retrieval + graph-enrichment to serve RAG-ready context

## Core data flow (keep this intact)

- Tree-sitter Java grammar build: `setup_java_language()` → `build/java-languages.so`
- Parsing: `JavaParser.parse_java_file()` uses tree-sitter queries + **`.captures()`** to emit `JavaMethod` objects
- Indexing: `index_java_methods()` converts methods to LangChain `Document` + metadata and calls `vectorstore.add_documents()`
- Retrieval: `GraphEnrichedRetriever` does similarity search then enriches results by following `calls`

## Non-obvious requirements / gotchas (do not break)

- `JavaParser.__init__` requires `build/java-languages.so`. Ensure `setup_java_language()` ran successfully before creating a parser.
- `setup_java_language()` needs external tools (git + build toolchain). Tests will **skip** if setup fails.
- Chroma metadata must be primitive types: `index_java_methods()` serializes `calls` as a **comma-separated string**.
  - `GraphEnrichedRetriever` must keep accepting both string and list-like `calls` (tests rely on this).
- Keep the LangChain import fallbacks (some envs require `langchain_community`): see `core/rag/embeddings.py` / `utils/chat.py`.

## App structure guidance (refactor target)

- When splitting the single script into a multi-module app, preserve behavior by moving code (don’t rewrite logic):
  - parser + tree-sitter setup: `setup_java_language()`, `JavaParser`, `JavaMethod`
  - indexing: `index_java_methods()` + configuration for `persist_directory` (default today is `./chroma_db`)
  - retrieval: `GraphEnrichedRetriever` + any serialization/parsing of `calls`
  - API layer: thin HTTP handlers that call “index”/“query” functions (no business logic in handlers)

## Entrypoints (current)

- Preferred entrypoints live at the repo root:
  - `app.py` (FastAPI)
  - `indexer.py` (CLI)
  - `config.py` (YAML config)

## Python environment (IMPORTANT)

- Always use the repo-local virtualenv in `./venv` when running any Python command in the terminal.
  - Use `./venv/bin/python` instead of `python`.
  - Use `./venv/bin/pip` instead of `pip`.
  - For module invocations: `./venv/bin/python -m <module>` (e.g., `./venv/bin/python -m unittest -v`).
  - If the venv is missing, create it with `python -m venv venv` and then install deps.

## Local workflows

- Install deps: `pip install -r requirements.txt`
- Run unit tests: `python -m unittest -v` (uses fixture `fixtures/SampleService.java`)
- Run lightweight validation: `python validate.py`

Note: Prefer the venv equivalents:
- `./venv/bin/pip install -r requirements.txt`
- `./venv/bin/python -m unittest -v`
- `./venv/bin/python validate.py`

## Environment variables

- `OPENAI_API_KEY`: required for embeddings + real retrieval demo (demo currently skips if not set)
- `OPENAI_API_BASE`: optional custom endpoint (passed to `create_embeddings(base_url=...)`)

## Change hygiene (what to update together)

- If you change method ID/signature/calls formatting or metadata keys, update all of:
  - `index_java_methods()` document content + metadata
  - `GraphEnrichedRetriever` enrichment + `calls` parsing
  - `test_java_graph_rag.py` expectations

## Concrete examples in this repo

- Parsing + call extraction patterns: `JavaParser.parse_java_file()` / `_extract_calls()` in `core/parsing/java_parser.py`
- Javadoc extraction pattern: `JavaParser._extract_javadoc()` (sibling lookup + raw-text fallback)
- Test fixture covering constructors, generics, and calls: `fixtures/SampleService.java`
