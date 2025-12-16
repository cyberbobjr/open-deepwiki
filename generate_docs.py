from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from dotenv import load_dotenv
from langchain_chroma import Chroma

from config import AppConfig, apply_config_to_env, configure_logging, load_config
from core.documentation.feature_extractor import (
    generate_module_summary,
    generate_project_overview,
    summarize_file_semantically,
)
from core.documentation.site_generator import write_feature_docs_site
from core.rag.embeddings import create_embeddings
from core.rag.indexing import index_project_overview
from indexer import iter_java_files
from utils.chat import create_chat_model


logger = logging.getLogger(__name__)


def _read_text_best_effort(path: Path) -> str:
    """Read a UTF-8 text file with best-effort error handling.

    Args:
        path: File path to read.

    Returns:
        File contents as a string; empty string if unreadable.
    """

    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Skipping unreadable file %s: %s", path, e)
        return ""


def _group_by_parent_folder(
    root_dir: Path,
    java_files: Iterable[Path],
) -> Dict[Path, List[Path]]:
    """Group Java files by their parent folder under a root directory.

    Args:
        root_dir: Root directory for the codebase.
        java_files: Iterable of Java file paths.

    Returns:
        Mapping of folder path -> list of Java file paths (sorted).
    """

    grouped: Dict[Path, List[Path]] = {}
    for file_path in java_files:
        try:
            parent = file_path.parent
        except Exception:
            continue
        grouped.setdefault(parent, []).append(file_path)

    for folder, files in grouped.items():
        grouped[folder] = sorted(files)

    return dict(sorted(grouped.items(), key=lambda kv: str(kv[0])))


def _folder_key(root_dir: Path, folder_path: Path) -> str:
    """Create a stable module key string for a folder under root."""

    try:
        rel = folder_path.resolve().relative_to(root_dir.resolve())
        return rel.as_posix() or "."
    except Exception:
        return str(folder_path)


def _get_vectorstore() -> Chroma:
    """Create a Chroma vector store using repo conventions.

    Returns:
        A configured Chroma vector store.

    Raises:
        ValueError: If embeddings configuration is missing.
    """

    persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "java_methods")

    base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
    embeddings = create_embeddings(base_url)

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )


def generate_docs(
    *,
    root_dir: Path,
    config: AppConfig,
    output_path: Path,
    site_output_dir: Optional[Path],
    index_into_chroma: bool,
    max_files: Optional[int],
) -> Path:
    """Generate a DeepWiki-style project overview markdown file.

    Args:
        root_dir: Root directory containing Java sources.
        config: Loaded application config (used for env + project name).
        output_path: Where to write the resulting markdown file.
        site_output_dir: Optional directory to write a feature-based docs site (docs/index.md, docs/features/*.md).
        index_into_chroma: If True, index the overview text into Chroma.
        max_files: Optional cap on number of Java files to summarize.

    Returns:
        The path written to (same as `output_path`).

    Raises:
        ValueError: If LLM configuration is missing.
        RuntimeError: If doc generation fails catastrophically.
    """

    llm = create_chat_model(
        base_url=os.getenv("OPENAI_CHAT_API_BASE"),
        model=os.getenv("OPENAI_CHAT_MODEL"),
        temperature=0.0,
        streaming=False,
    )

    java_paths = list(iter_java_files(str(root_dir)))
    if max_files is not None:
        java_paths = java_paths[: max(0, int(max_files))]

    logger.info("Found %d Java files under %s", len(java_paths), root_dir)

    grouped = _group_by_parent_folder(root_dir, java_paths)

    file_summaries_by_folder: Dict[Path, List[str]] = {}
    file_summaries_by_path: Dict[str, str] = {}
    total_files = 0

    for folder, files in grouped.items():
        summaries: List[str] = []
        for file_path in files:
            code = _read_text_best_effort(file_path)
            summary = summarize_file_semantically(file_path, code, llm)
            summaries.append(summary)
            file_summaries_by_path[str(file_path)] = summary
            total_files += 1
        file_summaries_by_folder[folder] = summaries

    logger.info("Generated %d file summaries", total_files)

    module_summaries: Dict[str, str] = {}
    for folder, summaries in file_summaries_by_folder.items():
        key = _folder_key(root_dir, folder)
        module_summaries[key] = generate_module_summary(folder, summaries, llm)

    overview = generate_project_overview(root_dir, module_summaries, llm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(overview, encoding="utf-8")
    logger.info("Wrote project overview to %s", output_path)

    if site_output_dir is not None:
        try:
            write_feature_docs_site(
                output_dir=site_output_dir,
                project_overview=overview,
                file_summaries=file_summaries_by_path,
                llm=llm,
                batch_size=10,
            )
            logger.info("Wrote feature docs site to %s", site_output_dir)
        except Exception as e:
            raise RuntimeError(
                f"Feature-based docs site generation failed: {type(e).__name__}: {e}"
            ) from e

    if index_into_chroma:
        project_name: Optional[str] = getattr(config, "project_name", None) or os.getenv(
            "OPEN_DEEPWIKI_PROJECT"
        )

        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

        vectorstore = _get_vectorstore()
        index_project_overview(project=project_name, overview_text=overview, vectorstore=vectorstore)

        persist = getattr(vectorstore, "persist", None)
        if callable(persist):
            persist()

        logger.info("Indexed project overview into Chroma (project=%s)", project_name)

    return output_path


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description="Generate DeepWiki-style project documentation")

    parser.add_argument(
            "--output-dir",
            default=None,
            help=(
                "Base output directory for generated docs. "
                "Defaults to config.docs_output_dir (or 'OUTPUT' if missing)."
            ),
        )
        parser.add_argument(
        "--root-dir",
            default=None,
            help=(
                "Where to write the generated overview markdown. "
                "Defaults to <output-dir>/PROJECT_OVERVIEW.md."
            ),
        default=None,
        help="Path to YAML config (defaults to OPEN_DEEPWIKI_CONFIG or open-deepwiki.yaml)",
    )
            default=None,
            help=(
                "Where to write a feature-based docs site (docs/index.md + docs/features/*.md). "
                "Defaults to <output-dir>/docs. Use --no-site to disable."
            ),
            f"(default: {DEFAULT_OUTPUT_DIR}/PROJECT_OVERVIEW.md)"
        ),
    )
    parser.add_argument(
        "--site-dir",
        default=f"{DEFAULT_OUTPUT_DIR}/docs",
        help=(
            "Where to write a feature-based docs site "
            f"(default: {DEFAULT_OUTPUT_DIR}/docs). Use --no-site to disable."
        ),
    )
    parser.add_argument(
        "--no-site",
        action="store_true",
        help="If set, do not generate the feature-based docs site.",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="If set, index the overview into Chroma (requires embeddings config)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional cap on number of Java files to summarize (useful for quick runs)",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for doc generation."""

    load_dotenv(override=False)

    args = _parse_args(argv)
    config = load_config(args.config)
    configure_logging(config.debug_level)
    apply_config_to_env(config)

    root_dir = Path(args.root_dir or config.java_codebase_dir).resolve()

        configured_output_dir = str(getattr(config, "docs_output_dir", "OUTPUT") or "OUTPUT")
        base_output_dir = Path(args.output_dir or configured_output_dir).expanduser()
        if not base_output_dir.is_absolute():
            base_output_dir = (Path.cwd() / base_output_dir).resolve()

        output_path = (
            Path(args.output).expanduser().resolve()
            if args.output
            else (base_output_dir / "PROJECT_OVERVIEW.md")
        )

        site_output_dir = None
        if not bool(args.no_site):
            site_output_dir = (
                Path(args.site_dir).expanduser().resolve()
                if args.site_dir
                else (base_output_dir / "docs")
            )

    try:
        generate_docs(
            root_dir=root_dir,
            config=config,
            output_path=output_path,
            site_output_dir=site_output_dir,
            index_into_chroma=bool(args.index),
            max_files=args.max_files,
        )
        return 0
    except Exception as e:
        logger.error("Doc generation failed: %s: %s", type(e).__name__, e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
