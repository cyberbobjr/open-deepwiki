from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Protocol

from dotenv import load_dotenv
from langchain_chroma import Chroma

from config import (AppConfig, apply_config_to_env, configure_logging,
                    load_config, prefetch_tiktoken_encodings)
from core.parsing.java_parser import JavaMethod, JavaParser
from core.parsing.tree_sitter_setup import setup_java_language
from core.rag.embeddings import create_embeddings
from core.rag.indexing import index_java_file_summaries, index_java_methods

logger = logging.getLogger(__name__)


class JavaParserLike(Protocol):
    """Structural type for parsers that can extract Java methods.

    This allows `scan_java_methods()` to be tested with a lightweight stub without
    requiring tree-sitter to be present.
    """

    def parse_java_file(self, java_code: str, *, file_path: Optional[str] = None) -> List[JavaMethod]:
        """Parse a Java source file and return extracted methods."""

        ...


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the indexer.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Parsed argparse namespace.
    """

    parser = argparse.ArgumentParser(description="Index a Java codebase into Chroma")
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
        help="Optional cap on number of Java files to summarize when generating docs",
    )
    return parser.parse_args(argv)


def _is_test_java_path(path: Path, *, root: Path) -> bool:
    """Return True when a Java file is located under a directory named "test".

    This is intentionally strict (no filename heuristics). Only paths whose
    relative components include a folder literally named "test" are excluded.

    Examples excluded:
        - src/test/java/com/example/Foo.java
        - test/com/example/Foo.java

    Examples included:
        - src/tests/java/... (folder "tests" is NOT excluded)
        - src/main/java/.../PaymentServiceTest.java (filename is NOT used)

    Args:
        path: Candidate filesystem path (file).
        root: Root directory being scanned.

    Returns:
        True if the path is under a "test" directory.
    """

    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        rel = path

    parts_lower = [p.lower() for p in rel.parts]
    return "test" in parts_lower


def iter_java_files(root_dir: str, *, exclude_tests: bool = True) -> Iterable[Path]:
    """Yield Java source files under a directory.

    Args:
        root_dir: Root directory to scan recursively.
        exclude_tests: If True (default), filters out Java files that are located
            under a directory named "test" (e.g., under src/test/java).

    Yields:
        Paths to discovered .java files.
    """

    root = Path(root_dir)
    if not root.exists():
        return []

    def _should_skip_dir(p: Path) -> bool:
        name = p.name
        if name in {".git", ".venv", "venv", "build", "vendor", "chroma_db", "__pycache__"}:
            return True
        if exclude_tests and name.lower() == "test":
            return True
        return False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(Path(dirpath) / d)]

        for filename in filenames:
            if not filename.endswith(".java"):
                continue

            path = Path(dirpath) / filename
            if exclude_tests and _is_test_java_path(path, root=root):
                continue
            yield path


def iter_resource_files(root_dir: str, extensions: List[str], exclude: Optional[List[str]] = None) -> Iterable[Path]:
    """Yield non-Java resource files under a directory.
    
    Args:
        root_dir: Root directory to scan.
        extensions: List of extensions to include (e.g. ['.yaml', '.json']).
        exclude: List of directory names to exclude (defaults to standard ignored dirs).
    """
    root = Path(root_dir)
    if not root.exists():
        return []

    exclude_dirs = {".git", ".venv", "venv", "build", "vendor", "chroma_db", "__pycache__", "target", "node_modules", "dist"}
    if exclude:
        exclude_dirs.update(exclude)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in extensions:
                 yield path


def scan_java_methods(
    codebase_dir: str,
    parser: JavaParserLike,
    *,
    exclude_tests: bool = True,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> List[JavaMethod]:
    """Scan a directory for Java files and parse methods/constructors.

    Args:
        codebase_dir: Root directory to scan.
        parser: Initialized JavaParser (tree-sitter backed).
        exclude_tests: If True (default), excludes Java files located under a directory
            named "test".
        progress_callback: Optional callback invoked during scanning to report progress.
            The callback is called as: (processed_files, total_files, current_file).
            - processed_files: Number of files completed so far.
            - total_files: Total number of Java files that will be scanned.
            - current_file: Path of the file that was just processed (or None at start).

    Returns:
        List of parsed JavaMethod objects.
    """

    methods: List[JavaMethod] = []

    files = list(iter_java_files(codebase_dir, exclude_tests=exclude_tests))
    total_files = len(files)
    logger.info("Scanning %d Java files under %s", total_files, codebase_dir)

    if progress_callback is not None:
        progress_callback(0, total_files, None)

    processed_files = 0

    for path in files:
        try:
            java_code = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Skipping unreadable file %s: %s", path, e)
            processed_files += 1
            if progress_callback is not None:
                progress_callback(processed_files, total_files, str(path))
            continue

        try:
            file_methods = parser.parse_java_file(java_code, file_path=str(path))
            methods.extend(file_methods)
        except Exception as e:
            logger.warning("Skipping unparsable file %s: %s", path, e)
            processed_files += 1
            if progress_callback is not None:
                progress_callback(processed_files, total_files, str(path))
            continue

        processed_files += 1
        if progress_callback is not None:
            progress_callback(processed_files, total_files, str(path))

    if progress_callback is not None:
        progress_callback(processed_files, total_files, "")

    if progress_callback is not None:
        progress_callback(processed_files, total_files, "")

    return methods


def scan_resource_files(
    codebase_dir: str,
    extensions: List[str],
    parser,
    chunk_size: int = 1000,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> List:
    """Scan a directory for resource files and parse them into Documents.
    
    Args:
        codebase_dir: Root to scan.
        extensions: List of extensions to include.
        parser: Initialized GenericAppParser.
        chunk_size: Token limit per chunk.
        progress_callback: Optional progress callback.
        
    Returns:
        List of LangChain Documents.
    """
    from langchain_core.documents import Document
    
    docs: List[Document] = []
    
    files = list(iter_resource_files(codebase_dir, extensions))
    total_files = len(files)
    logger.info("Scanning %d resource files under %s", total_files, codebase_dir)
    
    processed_files = 0
    if progress_callback:
        progress_callback(0, total_files, None)
        
    for path in files:
        try:
            file_docs = parser.parse_file(path, chunk_size=chunk_size)
            docs.extend(file_docs)
        except Exception as e:
            logger.warning("Failed to parse resource %s: %s", path, e)
            
        processed_files += 1
        if progress_callback:
            progress_callback(processed_files, total_files, str(path))
            
    if progress_callback:
        progress_callback(processed_files, total_files, "")
        
    return docs


def _get_vectorstore() -> Chroma:
    persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "java_methods")

    base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
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
    methods = scan_java_methods(
        config.java_codebase_dir,
        parser,
        exclude_tests=bool(getattr(config, "index_exclude_tests", True)),
    )

    project = getattr(config, "project_name", None) or os.getenv("OPEN_DEEPWIKI_PROJECT")
    if project:
        for m in methods:
            m.project = project

    if not methods:
        logger.warning("No Java methods found; nothing to index.")
        return 0

    vectorstore = _get_vectorstore()
    method_docs_map = index_java_methods(methods, vectorstore)

    if bool(getattr(config, "index_file_summaries", False)):
        index_java_file_summaries(methods, vectorstore)

    persist = getattr(vectorstore, "persist", None)
    if callable(persist):
        persist()

    logger.info("Indexed %d methods into Chroma", len(method_docs_map))
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
        "Indexing Java codebase dir=%s (config=%s)",
        config.java_codebase_dir,
        config_path or "open-deepwiki.yaml",
    )

    count = index_codebase(config)
    print(f"Indexed {count} methods")

    if bool(getattr(args, "generate_docs", False)):
        from generate_docs import generate_docs

        output_path = Path(str(getattr(args, "docs_output", "PROJECT_OVERVIEW.md"))).resolve()
        generate_docs(
            root_dir=Path(config.java_codebase_dir).resolve(),
            config=config,
            output_path=output_path,
            site_output_dir=None,
            index_into_chroma=bool(getattr(args, "docs_index", False)),
            max_files=getattr(args, "docs_max_files", None),
        )
        print(f"Wrote docs to {output_path}")


if __name__ == "__main__":
    main()
