# Java Graph RAG - Usage Examples

## Overview

This document provides examples of how to use the Java Graph RAG system.

## Prerequisites

Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Astuce (pour éviter les soucis conda/global) :
- si tu n’actives pas le venv, préfixe les commandes avec `./venv/bin/python`.

Set up environment variables (optional):

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://your-internal-api.example.com/v1"  # Optional custom URL

# If you use a custom gateway (recommended), set these explicitly (no implicit fallback):
export OPENAI_EMBEDDING_API_BASE="https://your-embeddings-gateway.example.com/v1"
export OPENAI_CHAT_API_BASE="https://your-llm-gateway.example.com/v1"

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

# Optional: prefetch encodings at startup (forces download/caching)
# Configure via YAML (recommended). There is no dedicated env var for this in open-deepwiki.
```

Optionnel: config YAML à la racine (par défaut `open-deepwiki.yaml`) :

```yaml
debug_level: INFO
java_codebase_dir: ./fixtures

# Optional: LLM endpoints
# If you need separate gateways, set these:
# embeddings_api_base: https://your-embeddings-gateway.example.com/v1
# chat_api_base: https://your-llm-gateway.example.com/v1

# Optional: custom root CA bundle (PEM) for outbound HTTPS
ssl_ca_file: /path/to/root-ca-bundle.pem

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

## Mode “application” (indexer + API)

### 1) Indexer un codebase Java

Indexe tous les `.java` du répertoire configuré (`java_codebase_dir`) et persiste dans Chroma (par défaut `./chroma_db`).

```bash
python indexer.py
# sans activer le venv :
./venv/bin/python indexer.py
```

Variables utiles :
- `CHROMA_PERSIST_DIR` (défaut `./chroma_db`)
- `CHROMA_COLLECTION` (défaut `java_methods`)
- `OPEN_DEEPWIKI_CONFIG` (chemin vers le YAML)

### 2) Lancer l’API

```bash
uvicorn app:app --reload --port 8000
# sans activer le venv :
./venv/bin/python -m uvicorn app:app --reload --port 8000
```

Endpoints :
- `GET /health`
- `POST /query` avec `{ "query": "...", "k": 4 }`
- `POST /ask` avec `{ "question": "...", "k": 4 }` (chat + contexte RAG)
- `POST /index-directory` avec `{ "path": "..." }` (indexation récursive des `.java`)

Implémentation : les routes sont dans `router/api.py` (montées par `app.py`).

Utilitaires : la création du vectorstore Chroma et le chargement du `method_docs_map` sont dans `utils/vectorstore.py`.

Exemple :

```bash
curl -X POST http://127.0.0.1:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"create user","k":4}'
```

Chat (réponse générée à partir du contexte RAG) :

```bash
curl -X POST http://127.0.0.1:8000/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"How do I create a new user?","k":4}'
```

Indexation récursive d’un répertoire (utile pour indexer un autre codebase que celui du YAML) :

```bash
curl -X POST http://127.0.0.1:8000/index-directory \
        -H 'Content-Type: application/json' \
        -d '{"path":"./fixtures"}'
```

Réponse (exemple) :

```json
{
    "path": "/abs/path/to/fixtures",
    "indexed_methods": 12,
    "loaded_method_docs": 12
}
```

Notes :
- `path` peut être absolu, ou relatif (résolu depuis le répertoire de lancement du serveur).
- Nécessite `OPENAI_API_KEY` (embeddings). Si absent : HTTP 503.

## Mode “démo script” (historique)

Le script tout-en-un `java_graph_rag.py` a été supprimé au profit de modules dédiés.
Utilise plutôt les entrypoints de l’application (`indexer.py` + `app.py`).

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
export OPENAI_API_BASE="https://your-internal-api.example.com/v1"
# puis lance l’API / l’indexer normalement
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
1. The `OPENAI_API_BASE` environment variable is set correctly
2. The endpoint is accessible
3. The API key is valid

### Mock mode

If dependencies are not fully installed, the script falls back to mock mode, which still demonstrates the concepts without actual parsing or vector search.
