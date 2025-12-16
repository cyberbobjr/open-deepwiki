# open-deepwiki — Usage

## Overview

This document provides examples of how to run the open-deepwiki backend + web UI, index Java projects, and call the HTTP API.

## Prerequisites

Install dependencies:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Tip (to avoid conda/global issues):
- If you don’t activate the venv, prefix commands with `./venv/bin/python`.

Set up environment variables (required for indexing/query/ask):

```bash
export OPENAI_API_KEY="your-api-key"

# If you use a custom gateway, set these explicitly:
export OPENAI_EMBEDDING_API_BASE="https://your-internal-api.example.com/v1"
export OPENAI_CHAT_API_BASE="https://your-internal-api.example.com/v1"

# Also set explicit models (no implicit defaults):
export OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
export OPENAI_CHAT_MODEL="gpt-4o-mini"

# Optional: custom root CA bundle (PEM) for outbound HTTPS
# Useful behind corporate proxies / custom PKI.
export SSL_CERT_FILE="/path/to/root-ca-bundle.pem"
export REQUESTS_CA_BUNDLE="/path/to/root-ca-bundle.pem"

# Optional: outbound proxy for downloads + API calls
# This is what you typically need for things like tiktoken encoding downloads.
export HTTP_PROXY="http://proxy.mycorp.local:3128"
export HTTPS_PROXY="http://proxy.mycorp.local:3128"
export NO_PROXY="127.0.0.1,localhost,.mycorp.local"

# Optional: control where tiktoken stores its cache/downloaded encoding files
export TIKTOKEN_CACHE_DIR="/abs/path/to/tiktoken-cache"

# Note: tiktoken does NOT cache files by their original filename.
# It stores each downloaded URL under:
#   $TIKTOKEN_CACHE_DIR/<sha1(url)>
# Example (compute the cache key):
#   ./venv/bin/python -c 'import hashlib; url="https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"; print(hashlib.sha1(url.encode()).hexdigest())'
# If you already have the encoding file offline, you can place it at:
#   $TIKTOKEN_CACHE_DIR/<that_sha1>
# and it will be used (as long as the file bytes match the expected SHA256 inside tiktoken).

# Optional: prefetch encodings at startup (forces download/caching)
# Configure via YAML (recommended). There is no dedicated env var for this in open-deepwiki.
```

Optional: YAML config at the repo root (default `open-deepwiki.yaml`):

```yaml
debug_level: INFO
java_codebase_dir: ./fixtures

# Optional: project scope name
# When set, indexed docs include metadata.project=<project_name>.
# Note: the HTTP API still requires an explicit `project` field in requests.
project_name: my-project

# Optional: index one heuristic summary document per Java file (helps file-level RAG)
index_file_summaries: true

# Optional: persist /ask conversation state via checkpointer
# The API uses this to keep agent memory across requests (keyed by session_id).
checkpointer_backend: sqlite
checkpointer_sqlite_path: ./checkpoints.sqlite3

# Optional: project graph persistence (big-picture)
project_graph_sqlite_path: ./project_graph.sqlite3

# Optional: LLM endpoints
# If you want a single URL for embeddings + chat, set only:
# llm_api_base: https://your-internal-api.example.com/v1

# Optional: custom root CA bundle (PEM) for outbound HTTPS
ssl_ca_file: /path/to/root-ca-bundle.pem

# Embeddings compatibility
# Some OpenAI-compatible embedding servers only accept string inputs.
# Set this to false to prevent sending token-id arrays.
embeddings_check_ctx_length: false

# If you're behind a corporate proxy that uses a self-signed / private CA:
# - Put the proxy's root CA certificate in a PEM file
# - Point `ssl_ca_file` to it
# This is the safe fix for CERTIFICATE_VERIFY_FAILED (instead of disabling TLS verification).

# Optional: outbound proxy for downloads + API calls
http_proxy: http://proxy.mycorp.local:3128
https_proxy: http://proxy.mycorp.local:3128
no_proxy: 127.0.0.1,localhost,.mycorp.local

# Optional: tiktoken cache directory
tiktoken_cache_dir: /abs/path/to/tiktoken-cache

# Optional: prefetch tiktoken encodings at startup (forces download/caching)
tiktoken_prefetch: true
tiktoken_prefetch_encodings:
    - cl100k_base
```

## Application mode (indexer + API)

### 1) Index a Java codebase

Indexes all `.java` files under the configured directory (`java_codebase_dir`) and persists to Chroma (default `./chroma_db`).

```bash
./venv/bin/python indexer.py
# (optional) point to a specific config file:
./venv/bin/python indexer.py --config open-deepwiki.yaml
```

Useful variables:
- `CHROMA_PERSIST_DIR` (default `./chroma_db`)
- `CHROMA_COLLECTION` (default `java_methods`)
- `OPEN_DEEPWIKI_CONFIG` (path to the YAML)

### 2) Run the API

```bash
# Recommended (uses api_port from open-deepwiki.yaml):
./venv/bin/python app.py

# Dev reload mode:
./venv/bin/python -m uvicorn app:app --reload --port 8000
```

Endpoints :
- `GET /api/v1/health`
- `GET /api/v1/projects` (list indexed project scopes)
- `GET /api/v1/projects/details` (projects + last known indexed path/timestamp)
- `DELETE /api/v1/projects` with body `{ "project": "..." }` (delete project scope)

- `POST /api/v1/index-directory` with `{ "path": "...", "project": "...", "reindex": true, "include_file_summaries": true }`
    (starts indexing asynchronously; returns `status: in_progress`)
- `GET /api/v1/index-status?project=...` (poll indexing status)

- `POST /api/v1/query` with `{ "query": "...", "k": 4, "project": "..." }`
- `POST /api/v1/ask` with `{ "question": "...", "k": 4, "project": "...", "session_id": "..." }`
- `POST /api/v1/ask/stream` (SSE)

- `POST /api/v1/sessions` with `{ "project": "..." }` (list chat sessions)
- `POST /api/v1/sessions/delete` with `{ "project": "...", "session_id": "..." }`

- `POST /api/v1/project-overview` with `{ "project": "..." }`
- `POST /api/v1/project-docs-index` with `{ "project": "..." }`
- `GET /api/v1/projects/{project}/docs/{doc_path}` (serve generated markdown)

- `POST /api/v1/generate-javadoc` and related job endpoints
- `GET /api/v1/postimplementation-logs` (read JavaDoc generation logs)

Implementation: routes are in `router/api.py` (mounted by `app.py`).

Utilities: Chroma vectorstore creation and method doc loading are in `utils/vectorstore.py`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"create user","k":4,"project":"my-project"}'
```


```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"How do I create a new user?","k":4,"project":"my-project"}'

# Continue the conversation with a session_id (returned in the previous response)
curl -X POST http://127.0.0.1:8000/api/v1/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"Where is validation done?","k":4,"project":"my-project","session_id":"<paste-session-id>"}'
```

Recursive directory indexing (useful to index a different codebase than the one in YAML):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/index-directory \
        -H 'Content-Type: application/json' \
    -d '{"path":"./fixtures","project":"my-project","reindex":true,"include_file_summaries":true}'
```

Example response (indexing is asynchronous):

```json
{
    "path": "/abs/path/to/fixtures",
    "project": "my-project",
    "indexed_methods": 0,
    "indexed_file_summaries": 0,
    "loaded_method_docs": 0,
    "indexed_at": "2025-01-01T00:00:00Z",
    "status": "in_progress"
}
```

Then poll until completion:

```bash
curl 'http://127.0.0.1:8000/api/v1/index-status?project=my-project'
```

Notes :
- `path` can be absolute or relative (resolved from the server working directory).
- Requires `OPENAI_API_KEY` (embeddings). If missing: HTTP 503.

## Web UI (recommended)

Run the backend (`./venv/bin/python app.py`), then:

```bash
cd front
npm install
npm run dev
```

Open the printed Vite URL (typically `http://localhost:5173`). While a project is indexing, the projects list shows the card in a disabled state with a spinner.

## Code Components

### 1. JavaParser - Tree-sitter Based Parsing

The `JavaParser` class uses tree-sitter to parse Java code:

```python
from core.parsing.java_parser import JavaParser

parser = JavaParser()
methods = parser.parse_java_file(java_source_code)

for method in methods:
    print(f"ID: {method.id}")
    print(f"Signature: {method.signature}")
    print(f"Type: {method.type}")  # "method" or "constructor"
    print(f"Calls: {method.calls}")
    print(f"Has Javadoc: {method.javadoc is not None}")
```

### 2. GraphEnrichedRetriever - Dependency-Aware Retrieval

The retriever performs two steps:
1. Vector search to find relevant methods
2. Fetch documentation for called methods (dependencies)

```python
from langchain_chroma import Chroma
from core.rag.retriever import GraphEnrichedRetriever
from core.rag.embeddings import create_embeddings

# Setup
embeddings = create_embeddings()
vectorstore = Chroma(
    collection_name="java_methods",
    embedding_function=embeddings
)

# Create retriever
retriever = GraphEnrichedRetriever(
    vectorstore=vectorstore,
    method_docs_map=method_docs_map,
    k=3  # Number of primary results
)

# Query
results = retriever.get_relevant_documents("How do I create a user?")

for doc in results:
    is_dependency = doc.metadata.get('is_dependency', False)
    if is_dependency:
        print(f"[DEPENDENCY] {doc.metadata['signature']}")
        print(f"Called from: {doc.metadata['called_from']}")
    else:
        print(f"[PRIMARY] {doc.metadata['signature']}")
```

### 3. Indexing Java Methods

Index parsed methods into the vector store:

```python
from core.rag.indexing import index_java_methods

# Parse Java code
parser = JavaParser()
methods = parser.parse_java_file(java_code)

# Index into vector store
method_docs_map = index_java_methods(methods, vectorstore)
```

### 4. Custom OpenAI Endpoint

Configure a custom internal OpenAI API URL:

```python
from core.rag.embeddings import create_embeddings

embeddings = create_embeddings(
    base_url="https://your-internal-api.example.com/v1"
)
```

Or via environment variable:

```bash
export OPENAI_EMBEDDING_API_BASE="https://your-internal-api.example.com/v1"
export OPENAI_CHAT_API_BASE="https://your-internal-api.example.com/v1"
# then start the API / indexer normally
```

## Key Features Demonstrated

### 1. Tree-sitter Parsing with .captures

The parser uses tree-sitter's `.captures()` API to extract information:

```python
query = self.java_language.query("""
    (method_declaration) @method
    (constructor_declaration) @constructor
""")

captures = query.captures(tree.root_node)

for node, capture_name in captures:
    # Process each method/constructor
    ...
```

### 2. Javadoc Extraction via Sibling Nodes

Javadoc comments are extracted by looking at sibling nodes:

```python
def _extract_javadoc(self, node: tree_sitter.Node, code: str) -> Optional[str]:
    """Extract Javadoc from sibling nodes."""
    parent = node.parent
    if not parent:
        return None
    
    # Find previous sibling
    node_index = ...
    prev_sibling = parent.children[node_index - 1]
    
    if prev_sibling.type == 'block_comment':
        comment_text = code[prev_sibling.start_byte:prev_sibling.end_byte]
        if comment_text.startswith('/**'):
            return comment_text
```

### 3. Method Call Extraction

Method calls are extracted using tree-sitter queries:

```python
query = self.java_language.query("""
    (method_invocation
        name: (identifier) @call_name)
""")

captures = query.captures(node)

for call_node, _ in captures:
    call_name = code[call_node.start_byte:call_node.end_byte]
    calls.append(call_name)
```

### 4. Graph-Based Context Enrichment

The retriever automatically enriches results with dependency documentation:

1. **Primary Search**: Find methods matching the query
2. **Dependency Fetch**: For each result, find methods it calls
3. **Context Enrichment**: Include dependency documentation in results

This provides richer context for understanding code behavior.

## Example Output

```
Query 1: How do I create a new user?
--------------------------------------------------------------------------------
Retrieved 4 documents (including dependencies):

[PRIMARY] Document 1:
Method: public String createUser(String username, String email)
Type: method
Calls: ['validateEmail', 'generateUserId', 'saveToDatabase']

[DEPENDENCY] Document 2:
Method: private void validateEmail(String email)
Type: method
Calls: []
Called from: public_string_createuser_string_username_string_email

[DEPENDENCY] Document 3:
Method: private String generateUserId()
Type: method
Calls: []
Called from: public_string_createuser_string_username_string_email

[DEPENDENCY] Document 4:
Method: private void saveToDatabase(String userId, String username, String email)
Type: method
Calls: ['execute']
Called from: public_string_createuser_string_username_string_email
```

## Architecture

```
┌─────────────────┐
│  Java Source    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  JavaParser     │ ← tree-sitter
│  (parse_java_   │   .captures()
│   file)         │   sibling lookup
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  JavaMethod[]   │ (ID, signature, type,
│                 │  calls, code, javadoc)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  index_java_    │
│  methods()      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Chroma Vector  │ ← OpenAIEmbeddings
│  Store          │   (custom URL)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  GraphEnriched  │ 1. Vector search
│  Retriever      │ 2. Fetch deps via "calls"
│                 │ 3. Enrich context
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Enriched       │ (primary + dependencies)
│  Results        │
└─────────────────┘
```

## Troubleshooting

### Tree-sitter-java not found

If you get an error about tree-sitter-java, ensure you have git installed:

```bash
git --version
```

The script will automatically clone tree-sitter-java on first run.

### OpenAI API errors

If you're using a custom endpoint, ensure:
1. You set explicit base URLs (no implicit fallback):
    - `OPENAI_EMBEDDING_API_BASE`
    - `OPENAI_CHAT_API_BASE`
2. You set explicit models:
    - `OPENAI_EMBEDDING_MODEL`
    - `OPENAI_CHAT_MODEL`
3. The endpoint is accessible from the machine running the backend (and uses a trusted TLS chain, or you configured `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`).
4. `OPENAI_API_KEY` is set.

Note: open-deepwiki does not have a “mock mode” fallback for indexing/querying; if required dependencies or config are missing, it fails fast with an error.
