from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

import argparse
import logging
import os
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from dotenv import load_dotenv
from langchain_chroma import Chroma

from config import (AppConfig, apply_config_to_env, configure_logging,
                    load_config, prefetch_tiktoken_encodings)
from core.parsing.factory import \
    ParserFactory  # Keep for setup_languages implicit usage if needed, or remove if unused. Actually setup_languages is imported.
from core.parsing.tree_sitter_setup import setup_languages
from core.rag.indexing import index_code_blocks, index_file_summaries

logger = logging.getLogger(__name__)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the indexer."""

    parser = argparse.ArgumentParser(description="Index a codebase into Chroma")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (defaults to OPEN_DEEPWIKI_CONFIG or open-deepwiki.yaml)",
    )
    parser.add_argument(
        "--generate-docs",
        action="store_true",
        help="If set, also generate PROJECT_OVERVIEW.md after indexing",
    )
    parser.add_argument(
        "--docs-output",
        default="PROJECT_OVERVIEW.md",
        help="Where to write the generated overview markdown (default: PROJECT_OVERVIEW.md)",
    )
    parser.add_argument(
        "--docs-index",
        action="store_true",
        help="If set, also index the generated overview into Chroma (requires embeddings config)",
    )
    parser.add_argument(
        "--docs-max-files",
        type=int,
        default=None,
        help="Optional cap on number of files to summarize when generating docs",
    )
    return parser.parse_args(argv)


from core.scanning.scanner import iter_source_files, scan_codebase
from utils.vectorstore import _get_vectorstore


def index_codebase(config: AppConfig) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

    # Keeping Java setup for now as it's the primary language supported
    # In future, we might want a generic setup_parsers()
    logger.info("Ensuring tree-sitter languages are built...")
    setup_languages()

    blocks = scan_codebase(
        config.codebase_dir,
        exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
    )

    project = getattr(config, "project_name", None) or os.getenv("OPEN_DEEPWIKI_PROJECT")
    if project:
        for b in blocks:
            b.project = project

    if not blocks:
        logger.warning("No code blocks found; nothing to index.")
        return 0

    vectorstore = _get_vectorstore()
    method_docs_map = index_code_blocks(blocks, vectorstore)

    if bool(getattr(config, "index_file_summaries", False)):
        index_file_summaries(blocks, vectorstore)

    # Rebuild Graph (SQLite)
    from core.project_graph import SqliteProjectGraphStore
    if getattr(config, "project_graph_sqlite_path", None):
        logger.info("Rebuilding project graph...")
        graph_path = str(config.project_graph_sqlite_path)
        graph_store = SqliteProjectGraphStore(sqlite_path=graph_path)
        graph_store.rebuild(project=project, methods=blocks)

    persist = getattr(vectorstore, "persist", None)
    if callable(persist):
        persist()

    logger.info("Indexed %d blocks into Chroma", len(method_docs_map))
    return len(method_docs_map)


def main(argv: Optional[List[str]] = None) -> None:
    load_dotenv(override=False)

    args = _parse_args(argv)
    config_path = args.config or os.getenv("OPEN_DEEPWIKI_CONFIG")
    config = load_config(config_path)
    configure_logging(config.debug_level)

    # Allow specifying LLM/embeddings settings in YAML config.
    apply_config_to_env(config)

    # Force-download/cache tiktoken encodings early if configured.
    prefetch_tiktoken_encodings(config)

    logger.info(
        "Indexing codebase dir=%s (config=%s)",
        config.codebase_dir,
        config_path or "open-deepwiki.yaml",
    )

    count = index_codebase(config)
    print(f"Indexed {count} code blocks")

    if bool(getattr(args, "generate_docs", False)):
        from generate_docs import generate_docs

        output_path = Path(str(getattr(args, "docs_output", "PROJECT_OVERVIEW.md"))).resolve()
        generate_docs(
            root_dir=Path(config.codebase_dir).resolve(),
            config=config,
            output_path=output_path,
            site_output_dir=None,
            index_into_chroma=bool(getattr(args, "docs_index", False)),
            max_files=getattr(args, "docs_max_files", None),
        )
        print(f"Wrote docs to {output_path}")


if __name__ == "__main__":
    main()
