# Copilot instructions - open-deepwiki

## Project Overview

open-deepwiki is a Java codebase indexing and RAG (Retrieval-Augmented Generation) API with a web UI. It parses Java code using tree-sitter, indexes methods into a persistent Chroma collection, and serves retrieval + chat endpoints via FastAPI.

**Core functionality:**
- **Indexing**: Scan Java directories into named project scopes with persistent vector storage
- **Retrieval**: Graph-enriched similarity search that follows method call dependencies
- **Chat**: RAG-powered Q&A with streaming support (SSE) and conversation history
- **Documentation**: Auto-generate project documentation during indexing
- **Web UI**: Vue + Vite frontend for project management and chat interface

This repo evolved from a demo script into a production-ready application with an indexing entrypoint (CLI/job) and a query API (HTTP) that runs retrieval + graph-enrichment to serve RAG-ready context.

## Code Standards

### Required Documentation and Typing (MANDATORY)

- All public functions, methods, and classes MUST have a pydoc-style docstring.
  - Describe what it does in 1-3 sentences.
  - Document every argument (name + meaning + constraints).
  - Document return value(s) and what they represent.
  - Document raised exceptions when applicable.
- Type hints are mandatory:
  - Every function/method argument MUST be typed.
  - Every function/method MUST declare a return type.
  - Prefer precise types (e.g., `Optional[str]`, `Sequence[JavaMethod]`, `Dict[str, Any]`) over `Any`.
  - Add types for local variables when it materially improves clarity or when inference is non-obvious.
  - Do not introduce untyped containers like `list`/`dict`; use `list[str]`, `dict[str, int]`, etc.
- Keep docstrings and types consistent with runtime behavior (no stale docs).

### Code Style

- Don't add comments unless they match the style of other comments in the file or are necessary to explain complex changes.
- Use existing libraries whenever possible, and only add new libraries or update library versions if absolutely necessary.
- Follow Python best practices and idiomatic patterns.

## Development Flow

### Required Before Each Commit
- Always use the repo-local virtualenv in `./venv` when running any Python command
- Run tests before committing: `./venv/bin/python -m unittest -v`
- For significant changes, run validation: `./venv/bin/python validate.py` (if it exists)

### Setup and Installation
```bash
# Create and activate virtual environment
python3 -m venv venv

# Install dependencies
./venv/bin/pip install -r requirements.txt
```

### Build Commands
- **Install deps**: `./venv/bin/pip install -r requirements.txt`
- **Run backend API**: `./venv/bin/python app.py`
- **Run indexer CLI**: `./venv/bin/python indexer.py --config open-deepwiki.yaml`
- **Run tests**: `./venv/bin/python -m unittest -v`
- **Run validation**: `./venv/bin/python validate.py` (lightweight validation, if exists)
- **Frontend setup**: `cd front && npm install && npm run dev`

### Important: Use Virtual Environment
- Always use `./venv/bin/python` instead of `python`
- Always use `./venv/bin/pip` instead of `pip`
- For module invocations: `./venv/bin/python -m <module>` (e.g., `./venv/bin/python -m unittest -v`)
- If the venv is missing, create it with `python -m venv venv` and then install deps

## Repository Structure

### Entry Points (Root Level)
- `app.py`: FastAPI application factory + runner
- `indexer.py`: CLI indexer for batch indexing and docs generation
- `config.py`: YAML config loader + strict environment mapping
- `generate_docs.py`: Documentation generation utilities

### Core Modules
- `core/parsing/`: Java parsing with tree-sitter
  - `tree_sitter_setup.py`: Tree-sitter Java grammar build (`setup_java_language()`)
  - `java_parser.py`: `JavaParser` class - parses Java files and extracts `JavaMethod` objects
- `core/rag/`: RAG components
  - `indexing.py`: `index_java_methods()` - converts methods to LangChain Documents
  - `retriever.py`: `GraphEnrichedRetriever` - similarity search + dependency enrichment
  - `embeddings.py`: `create_embeddings()` - OpenAI embeddings factory
- `core/project_graph/`: Project graph management (SQLite-backed)
- `router/`: API routes (mounted under `/api/v1` in app.py)
  - `api.py`: Router aggregation
  - `routes_*.py`: Individual endpoint modules
- `services/`: Business logic services
- `utils/`: Utilities (vectorstore, chat, etc.)
- `tests/`: Unit and integration tests
- `fixtures/`: Test fixtures (e.g., `SampleService.java`)
- `front/`: Vue + Vite web UI

### Runtime State and Persistence
- **Chroma**: persistent vectorstore (`CHROMA_PERSIST_DIR`, default `./chroma_db`)
- **Project graph**: SQLite store for call graph (`project_graph_sqlite_path`)
- **Chat sessions**: SQLite checkpointer (`checkpointer_sqlite_path`)
- **Generated docs**: written under `docs_output_dir/<project>/docs/` (default `OUTPUT/<project>/docs/`)

## Core Data Flow (Keep This Intact)

- Tree-sitter Java grammar build: `setup_java_language()` → `build/java-languages.so`
- Parsing: `JavaParser.parse_java_file()` uses tree-sitter queries + **`.captures()`** to emit `JavaMethod` objects
- Indexing: `index_java_methods()` converts methods to LangChain `Document` + metadata and calls `vectorstore.add_documents()`
- Retrieval: `GraphEnrichedRetriever` does similarity search then enriches results by following `calls`

## Non-Obvious Requirements / Gotchas (Do Not Break)

- `JavaParser.__init__` requires `build/java-languages.so`. Ensure `setup_java_language()` ran successfully before creating a parser.
- `setup_java_language()` needs external tools (git + build toolchain). Tests will **skip** if setup fails.
- Chroma metadata must be primitive types: `index_java_methods()` serializes `calls` as a **comma-separated string**.
  - `GraphEnrichedRetriever` must keep accepting both string and list-like `calls` (tests rely on this).
- Use a single canonical import for LangChain OpenAI integrations (no multi-tier fallbacks):
  - `from langchain_openai import OpenAIEmbeddings` in `core/rag/embeddings.py`
  - `from langchain_openai import ChatOpenAI` in `utils/chat.py`

## Strict Configuration (No Silent Fallback)

- Do not introduce implicit fallbacks for LLM/embeddings endpoints or models.
  - Embeddings must use an explicit base URL (`OPENAI_EMBEDDING_API_BASE` or `llm_api_base` in YAML) and explicit model (`OPENAI_EMBEDDING_MODEL` / `embeddings_model`).
  - Chat must use an explicit base URL (`OPENAI_CHAT_API_BASE` or `llm_api_base` in YAML) and explicit model (`OPENAI_CHAT_MODEL` / `chat_model`).
- If a required value is missing, fail fast with a clear error (do not silently fall back to `OPENAI_API_BASE` or built-in default models).

## Environment Variables

Required for embeddings + retrieval:
- `OPENAI_API_KEY`: required for embeddings and chat
- `OPENAI_EMBEDDING_MODEL`: explicit model name (no defaults)
- `OPENAI_CHAT_MODEL`: explicit model name (no defaults)

Optional:
- `OPENAI_EMBEDDING_API_BASE`: custom endpoint for embeddings
- `OPENAI_CHAT_API_BASE`: custom endpoint for chat
- `OPENAI_API_BASE`: optional custom endpoint (passed to `create_embeddings(base_url=...)`)
- `CHROMA_PERSIST_DIR`: Chroma database directory (default: `./chroma_db`)
- `CHROMA_COLLECTION`: Collection name (default: `java_methods`)
- `OPEN_DEEPWIKI_CONFIG`: Path to YAML config file

You can also configure these via YAML (see `open-deepwiki.yaml.sample`).

## Key Guidelines

1. **Preserve behavior when refactoring**: When splitting code into modules, move code (don't rewrite logic):
   - parser + tree-sitter setup: `setup_java_language()`, `JavaParser`, `JavaMethod`
   - indexing: `index_java_methods()` + configuration for `persist_directory` (default today is `./chroma_db`)
   - retrieval: `GraphEnrichedRetriever` + any serialization/parsing of `calls`
   - API layer: thin HTTP handlers that call "index"/"query" functions (no business logic in handlers)

2. **Maintain data consistency**: If you change method ID/signature/calls formatting or metadata keys, update all of:
   - `index_java_methods()` document content + metadata
   - `GraphEnrichedRetriever` enrichment + `calls` parsing
   - `test_java_graph_rag.py` expectations

3. **Write comprehensive tests**: Write unit tests for new functionality. Use table-driven tests when possible.

4. **Follow existing patterns**: 
   - Parsing + call extraction patterns: `JavaParser.parse_java_file()` / `_extract_calls()` in `core/parsing/java_parser.py`
   - Javadoc extraction pattern: `JavaParser._extract_javadoc()` (sibling lookup + raw-text fallback)
   - Test fixture covering constructors, generics, and calls: `fixtures/SampleService.java`

5. **Maintain strict typing**: Keep all docstrings and type hints up to date with runtime behavior.

## API Endpoints

The API router is mounted under the `/api/v1` prefix in `app.py`.

Key endpoints:
- `/health`: configuration + startup diagnostics
- `/index-directory` + `/index-status`: async indexing job control and polling
- `/projects`, `/projects/details`, `DELETE /projects`: project discovery + lifecycle
- `/query`: similarity search (GraphEnrichedRetriever)
- `/ask` and `/ask/stream`: chat endpoints (SSE streaming supported)
- `/sessions` and `/sessions/delete`: session listing + deletion (SQLite-backed)
- `/project-overview`, `/project-docs-index`, `/projects/{project}/docs/{doc_path}`: generated docs serving

## Concrete Implementation Examples

- **Parsing + call extraction**: See `JavaParser.parse_java_file()` and `_extract_calls()` in `core/parsing/java_parser.py`
- **Javadoc extraction**: See `JavaParser._extract_javadoc()` - uses sibling lookup + raw-text fallback
- **Test fixture**: `fixtures/SampleService.java` covers constructors, generics, and calls
- **Graph enrichment**: `GraphEnrichedRetriever` in `core/rag/retriever.py` shows how to enrich results by following `calls`

## Testing

- Run all tests: `./venv/bin/python -m unittest -v`
- Tests use fixture `fixtures/SampleService.java`
- Tests will skip if tree-sitter setup fails (requires git + build toolchain)
- Always validate that changes don't break existing behavior

## Security Considerations

- Never commit secrets into source code
- Configuration values with secrets should come from environment variables or secure config files
- Be careful with LLM API endpoints and ensure they use proper TLS verification
- Follow secure coding practices for user input handling
