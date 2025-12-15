# Implementation Summary

## Java Graph RAG (script + application)

This document summarizes the implementation of the Java Graph RAG system.

This repository contains:
- an application (indexer + API) with root-level entrypoints: `indexer.py` and `app.py`
- separate “core” modules (parser/indexing/retriever/etc.) used by the application

### Requirements Met

✅ **1. Tree-sitter Java Parsing (tree-sitter==0.21.3)**
- Uses `.captures()` API for extracting AST nodes
- Extracts method/constructor ID, signature, type, calls, code
- Implements Javadoc extraction via sibling node lookup
- Files: `core/parsing/tree_sitter_setup.py`, `core/parsing/java_parser.py`

✅ **2. LangChain GraphEnrichedRetriever**
- Custom retriever extending `BaseRetriever`
- Performs vector similarity search
- Fetches dependency documentation via "calls" metadata IDs
- Enriches context with related method implementations
- File: `core/rag/retriever.py`

✅ **3. Chroma & OpenAIEmbeddings**
- Uses Chroma as vector store
- Configures OpenAIEmbeddings with custom internal URL support
- Supports `base_url` parameter for custom endpoints
- Files: `core/rag/embeddings.py`, `utils/vectorstore.py`

✅ **4. Validation & tests**
- Unit tests via `test_java_graph_rag.py` (fixtures)
- `validate.py` script adapted to the modular structure

### File Structure

```
open-deepwiki/
├── app.py                 # Entrypoint API (FastAPI)
├── indexer.py             # Indexing entrypoint (CLI)
├── config.py              # Config YAML + logging
├── core/                  # Core library (Python package)
│   ├── parsing/            # Java parser (tree-sitter)
│   └── rag/                # Embeddings + indexing + retriever
├── router/                # Routes FastAPI (endpoints HTTP)
├── utils/                 # Helpers (vectorstore, chat)
├── fixtures/              # Java fixtures for tests
├── tests/                 # Unit tests (unittest)
├── requirements.txt        # Dependencies
├── README.md
├── USAGE.md
├── validate.py
└── open-deepwiki.yaml.sample
```

### Key Components

#### 1. JavaParser Class
- Initializes tree-sitter with Java language
- `parse_java_file()`: Main parsing method
- `_extract_signature()`: Extracts method signature
- `_extract_calls()`: Finds method invocations using `.captures()`
- `_extract_javadoc()`: Retrieves Javadoc from sibling nodes
- `_generate_id()`: Creates unique method identifier

#### 2. GraphEnrichedRetriever Class
- Extends LangChain's `BaseRetriever`
- `_get_relevant_documents()`: Two-step retrieval:
  1. Vector search for primary matches
  2. Dependency enrichment via "calls" metadata
- Returns both primary results and their dependencies

#### 3. Helper Functions
- `setup_java_language()`: Downloads and builds tree-sitter-java
- `create_embeddings()`: Configures OpenAI embeddings with custom URL
- `index_java_methods()`: Indexes parsed methods into Chroma

Notes:
- The application loads the vector store via `utils/vectorstore.py` and exposes endpoints via `router/api.py`.

#### 4. Mock Data
- Complete Java class (`UserService`) with:
  - Package and imports
  - Multiple methods with Javadoc
  - Method calls between methods
  - Constructor
  - Private and public methods
  - Realistic business logic

### Technical Highlights

1. **Tree-sitter Usage**
   - Correctly uses `.captures()` API (not deprecated `.matches()`)
   - Implements sibling node lookup for Javadoc
   - Handles both methods and constructors

2. **Graph-Based Enrichment**
   - Follows "calls" metadata to fetch dependencies
   - Avoids duplicate results with seen_ids set
   - Marks dependencies with metadata

3. **Security & Best Practices**
   - No hardcoded credentials
   - Explicit `shell=False` in subprocess calls
   - Timeout protection for git operations
   - Uses object identity (`is`) for node comparison
   - Updated to non-deprecated OpenAI API parameters

4. **Validation**
   - Syntax validation passes
   - The repo includes scripts/tests to validate parsing + indexing + retrieval

### Testing

The implementation includes:
- `validate.py`: Validates all requirements are met
- `test_java_graph_rag.py`: Unit tests for components
- Comprehensive demo in `__main__` with 3 test queries

### Usage

“Application” mode (indexer + API):

```bash
pip install -r requirements.txt
python indexer.py
uvicorn app:app --reload --port 8000
```

“Demo script” mode (historical): removed (modular refactor).

With custom OpenAI endpoint:
```bash
export OPENAI_API_BASE="https://internal.api.com/v1"
export OPENAI_API_KEY="your-key"
python indexer.py
```

### Dependencies

Main dependencies (see `requirements.txt` for the source of truth):
- tree-sitter==0.21.3
- langchain (+ split packages : langchain-core, langchain-openai, langchain-chroma, ...)
- chromadb
- openai (SDK)
- tiktoken

### Code Quality

- **Documentation**: docstrings + docs (README/USAGE)
- **Type Hints**: Full type annotations
- **Error Handling**: Graceful fallbacks
- **Compat**: no more `api/` shim; the supported entrypoints are at the repo root (`app.py`, `indexer.py`).

### Deliverables

Main deliverables:
1. ✅ Python script for Java Graph RAG
2. ✅ Tree-sitter parsing with `.captures()`
3. ✅ GraphEnrichedRetriever implementation
4. ✅ Chroma + OpenAIEmbeddings with custom URL
5. ✅ Mock Java data
6. ✅ Indexing logic
7. ✅ Test queries in `__main__`
8. ✅ FastAPI API + indexer CLI (root-level entrypoints)
9. ✅ Documentation (README.md, USAGE.md)
10. ✅ Validation tools
