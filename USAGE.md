# Java Graph RAG - Usage Examples

## Overview

This document provides examples of how to use the Java Graph RAG system.

## Prerequisites

Install dependencies:

```bash
pip install -r requirements.txt
```

Set up environment variables (optional):

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://your-internal-api.example.com/v1"  # Optional custom URL
```

## Running the Demo

The script includes a complete demo with mock data:

```bash
python java_graph_rag.py
```

This will:
1. Set up tree-sitter Java parser
2. Parse mock Java code
3. Extract method information (ID, signature, type, calls, code, Javadoc)
4. Index methods into Chroma vector store
5. Create a GraphEnrichedRetriever
6. Run test queries demonstrating dependency enrichment

## Code Components

### 1. JavaParser - Tree-sitter Based Parsing

The `JavaParser` class uses tree-sitter to parse Java code:

```python
from java_graph_rag import JavaParser

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
from langchain.vectorstores import Chroma
from java_graph_rag import GraphEnrichedRetriever, create_embeddings

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
from java_graph_rag import index_java_methods

# Parse Java code
parser = JavaParser()
methods = parser.parse_java_file(java_code)

# Index into vector store
method_docs_map = index_java_methods(methods, vectorstore)
```

### 4. Custom OpenAI Endpoint

Configure a custom internal OpenAI API URL:

```python
from java_graph_rag import create_embeddings

embeddings = create_embeddings(
    base_url="https://your-internal-api.example.com/v1"
)
```

Or via environment variable:

```bash
export OPENAI_API_BASE="https://your-internal-api.example.com/v1"
python java_graph_rag.py
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
