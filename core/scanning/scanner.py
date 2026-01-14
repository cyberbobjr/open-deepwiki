from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional

from core.parsing.factory import ParserFactory
from core.parsing.models import CodeBlock
from core.ports.scan_port import CodebaseScanner, ScanProgressCallback

if TYPE_CHECKING:
    from core.parsing.generic_parser import GenericAppParser

logger = logging.getLogger(__name__)


def _is_test_path(path: Path, *, root: Path) -> bool:
    """Return True when a file is located under a directory named "test"."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        rel = path

    parts_lower = [p.lower() for p in rel.parts]
    return "test" in parts_lower


class FileSystemScanner(CodebaseScanner):
    """File system implementation of the CodebaseScanner."""

    def iter_files(self, root_dir: Path, exclude_tests: bool = True) -> Iterable[Path]:
        """Yield source files supported by the ParserFactory under a directory."""
        if not root_dir.exists():
            return []

        supported_extensions = set(ParserFactory.get_supported_extensions())

        def _should_skip_dir(p: Path) -> bool:
            name = p.name
            if name in {".git", ".venv", "venv", "build", "vendor", "chroma_db", "__pycache__", "node_modules"}:
                return True
            if exclude_tests and name.lower() == "test":
                return True
            return False

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(Path(dirpath) / d)]

            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix.lower() not in supported_extensions:
                    continue

                if exclude_tests and _is_test_path(path, root=root_dir):
                    continue
                yield path

    def scan(
        self,
        root_dir: Path,
        exclude_tests: bool = True,
        progress_callback: Optional[ScanProgressCallback] = None,
    ) -> List[CodeBlock]:
        """Scan a directory for supported source files and parse accessible code blocks."""

        blocks: List[CodeBlock] = []

        files = list(self.iter_files(root_dir, exclude_tests=exclude_tests))
        total_files = len(files)
        logger.info("Scanning %d source files under %s", total_files, root_dir)

        if progress_callback is not None:
            progress_callback(0, total_files, None)

        processed_files = 0

        for path in files:
            parser = ParserFactory.get_parser(str(path))
            if not parser:
                continue

            try:
                code = path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Skipping unreadable file %s: %s", path, e)
                processed_files += 1
                if progress_callback is not None:
                    progress_callback(processed_files, total_files, str(path))
                continue

            try:
                file_blocks = parser.parse_file(code, file_path=str(path))
                blocks.extend(file_blocks)
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

        return blocks

# Legacy global functions for backward compatibility (if needed by other modules temporarily)
def iter_source_files(root_dir: str, *, exclude_tests: bool = True) -> Iterable[Path]:
    scanner = FileSystemScanner()
    return scanner.iter_files(Path(root_dir), exclude_tests=exclude_tests)

def scan_codebase(
    codebase_dir: str,
    *,
    exclude_tests: bool = True,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> List[CodeBlock]:
    scanner = FileSystemScanner()
    return scanner.scan(Path(codebase_dir), exclude_tests=exclude_tests, progress_callback=progress_callback)

def iter_resource_files(root_dir: str, extensions: List[str], exclude: Optional[List[str]] = None) -> Iterable[Path]:
    """Yield non-source resource files under a directory."""
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

def scan_resource_files(
    codebase_dir: str,
    extensions: List[str],
    parser: "GenericAppParser",
    chunk_size: int = 1000,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> List:
    """Scan a directory for resource files and parse them into Documents."""
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
