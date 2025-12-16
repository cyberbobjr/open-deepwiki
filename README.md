# open-deepwiki

open-deepwiki is a Java codebase indexing + RAG API with a small web UI.

It parses Java using tree-sitter, indexes methods (and optional file summaries) into a persistent Chroma collection, and serves retrieval + chat endpoints via FastAPI.

## What you get

- **Indexing**: scan a directory of `.java` files into a named **project** scope
- **Retrieval**: `POST /api/v1/query` returns similarity matches enriched with called dependencies
- **Chat**: `POST /api/v1/ask` and `POST /api/v1/ask/stream` (SSE)
- **Docs**: indexing can generate per-project docs under `OUTPUT/<project>/docs/` and serve them via the API
- **Web UI**: a Vite + Vue front-end to index projects and chat

## Requirements

- Python **3.10+**
- Node.js 18+ (only for the web UI)
- Build toolchain for tree-sitter grammar build (git + a C/C++ compiler toolchain)

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Configuration (no silent fallbacks)

At minimum you must provide:

- `OPENAI_API_KEY`
- `OPENAI_EMBEDDING_MODEL`
- `OPENAI_CHAT_MODEL`

If you use OpenAI-compatible gateways, configure explicit base URLs:

- `OPENAI_EMBEDDING_API_BASE`
- `OPENAI_CHAT_API_BASE`

You can also configure these via YAML (see `open-deepwiki.yaml.sample`) and point the app to it with `OPEN_DEEPWIKI_CONFIG`.

## Run the backend

```bash
./venv/bin/python app.py
```

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## Run the web UI

```bash
cd front
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000`.

## Index a project

Use the UI to start indexing (project name + directory). While indexing runs, the project card shows as disabled with a spinner.

You can also use the CLI indexer:

```bash
./venv/bin/python indexer.py --config open-deepwiki.yaml
```

## API and examples

See [USAGE.md](USAGE.md) for endpoint list and curl examples.