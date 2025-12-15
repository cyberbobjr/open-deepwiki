from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from langchain_chroma import Chroma

from config import AppConfig, apply_config_to_env, configure_logging, load_config
from core.parsing.java_parser import JavaMethod, JavaParser
from core.rag.embeddings import create_embeddings
from core.rag.indexing import index_java_methods
from core.parsing.tree_sitter_setup import setup_java_language


logger = logging.getLogger(__name__)


def iter_java_files(root_dir: str) -> Iterable[Path]:
    root = Path(root_dir)
    if not root.exists():
        return []

    def _should_skip_dir(p: Path) -> bool:
        name = p.name
        return name in {".git", ".venv", "venv", "build", "vendor", "chroma_db", "__pycache__"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(Path(dirpath) / d)]

        for filename in filenames:
            if filename.endswith(".java"):
                yield Path(dirpath) / filename


def scan_java_methods(codebase_dir: str, parser: JavaParser) -> List[JavaMethod]:
    methods: List[JavaMethod] = []

    files = list(iter_java_files(codebase_dir))
    logger.info("Scanning %d Java files under %s", len(files), codebase_dir)

    for path in files:
        try:
            java_code = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Skipping unreadable file %s: %s", path, e)
            continue

        try:
            methods.extend(parser.parse_java_file(java_code))
        except Exception as e:
            logger.warning("Skipping unparsable file %s: %s", path, e)
            continue

    return methods


def _get_vectorstore() -> Chroma:
    persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "java_methods")

    base_url = os.getenv("OPENAI_API_BASE")
    embeddings = create_embeddings(base_url)

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )


def index_codebase(config: AppConfig) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

    logger.info("Ensuring tree-sitter Java grammar is built...")
    setup_java_language()

    parser = JavaParser()
    methods = scan_java_methods(config.java_codebase_dir, parser)

    if not methods:
        logger.warning("No Java methods found; nothing to index.")
        return 0

    vectorstore = _get_vectorstore()
    method_docs_map = index_java_methods(methods, vectorstore)

    persist = getattr(vectorstore, "persist", None)
    if callable(persist):
        persist()

    logger.info("Indexed %d methods into Chroma", len(method_docs_map))
    return len(method_docs_map)


def main() -> None:
    load_dotenv(override=False)

    config_path = os.getenv("OPEN_DEEPWIKI_CONFIG")
    config = load_config(config_path)
    configure_logging(config.debug_level)

    # Allow specifying LLM/embeddings settings in YAML config.
    apply_config_to_env(config)

    logger.info(
        "Indexing Java codebase dir=%s (config=%s)",
        config.java_codebase_dir,
        config_path or "open-deepwiki.yaml",
    )

    count = index_codebase(config)
    print(f"Indexed {count} methods")


if __name__ == "__main__":
    main()
