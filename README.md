# open-deepwiki

## Java Graph RAG

A Retrieval-Augmented Generation (RAG) system for Java codebases that uses graph-based dependency enrichment.

### Features

1. **Tree-sitter Parsing**: Parses Java code using `tree-sitter==0.21.3` to extract:
   - Method/Constructor ID
   - Signature
   - Type (method or constructor)
   - Called methods
   - Full code
   - Javadoc documentation (via sibling node lookup)

2. **GraphEnrichedRetriever**: A custom LangChain retriever that:
   - Performs vector similarity search
   - Fetches dependency documentation via "calls" metadata
   - Enriches context with related method implementations

3. **Vector Storage**: Uses Chroma with OpenAI embeddings
   - Supports custom internal OpenAI API URLs
   - Persistent storage for indexed methods

4. **Demo**: Includes mock Java data, indexing logic, and test queries

### Installation

```bash
pip install -r requirements.txt
```

### Usage

Basic usage with mock data:

```bash
python java_graph_rag.py
```

With custom OpenAI API endpoint:

```bash
export OPENAI_API_BASE="https://your-internal-api.example.com/v1"
export OPENAI_API_KEY="your-api-key"
python java_graph_rag.py
```

### How It Works

1. **Parsing**: The script uses tree-sitter to parse Java code and extract method information using the `.captures` API.

2. **Indexing**: Each method is indexed into a Chroma vector store with metadata including:
   - Method ID and signature
   - Type (method/constructor)
   - List of called methods
   - Javadoc availability

3. **Retrieval**: When querying:
   - Vector search finds relevant methods
   - The retriever follows "calls" metadata to fetch dependency documentation
   - Results include both primary matches and their dependencies

4. **Context Enrichment**: The GraphEnrichedRetriever automatically includes documentation for methods that are called by the retrieved methods, providing richer context for understanding the code.

### Example

The included mock data demonstrates a `UserService` class with methods for user management. Test queries show how the retriever can:

- Find the main method for creating users
- Identify validation methods called during user creation
- Retrieve database connection validation logic

### Architecture

```
JavaParser (tree-sitter)
    ↓
JavaMethod objects (ID, signature, type, calls, code, javadoc)
    ↓
Index to Chroma (with OpenAIEmbeddings)
    ↓
GraphEnrichedRetriever
    ↓
Enriched Results (primary + dependencies)
```

### Requirements

- Python 3.8+
- tree-sitter==0.21.3
- langchain
- chromadb
- openai
- Git (for cloning tree-sitter-java)