import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

import argparse
import logging
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from config import (AppConfig, apply_config_to_env, configure_logging,
                    load_config)
from core.documentation.pipeline import run_documentation_pipeline

logger = logging.getLogger(__name__)


def generate_docs(
    *,
    root_dir: Path,
    config: AppConfig,
    output_path: Path,
    site_output_dir: Optional[Path],
    index_into_chroma: bool,
    max_files: Optional[int],
) -> Path:
    """Wrapper for the core documentation pipeline."""
    return run_documentation_pipeline(
        root_dir=root_dir,
        config=config,
        output_path=output_path,
        site_output_dir=site_output_dir,
        index_into_chroma=index_into_chroma,
        max_files=max_files,
    )


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description="Generate DeepWiki-style project documentation")

    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (defaults to OPEN_DEEPWIKI_CONFIG or open-deepwiki.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Base output directory for generated docs. "
            "Defaults to config.docs_output_dir (or 'OUTPUT' if missing)."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Where to write the generated overview markdown. "
            "Defaults to <output-dir>/PROJECT_OVERVIEW.md."
        ),
    )
    parser.add_argument(
        "--root-dir",
        default=None,
        help="Root directory to scan (overrides config.codebase_dir).",
    )
    parser.add_argument(
        "--site-dir",
        default=None,
        help=(
            "Where to write a feature-based docs site (docs/index.md + docs/features/*.md). "
            "Defaults to <output-dir>/docs. Use --no-site to disable."
        ),
    )
    parser.add_argument(
        "--no-site",
        action="store_true",
        help="If set, do not generate the feature-based docs site.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="If set, skip indexing the overview into Chroma (enabled by default)",
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

    root_dir = Path(args.root_dir or config.codebase_dir).resolve()

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
            index_into_chroma=not bool(args.no_index),
            max_files=args.max_files,
        )
        return 0
    except Exception as e:
        logger.error("Doc generation failed: %s: %s", type(e).__name__, e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
