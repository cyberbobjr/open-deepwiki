import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.scanning.scanner import iter_source_files

logger = logging.getLogger(__name__)

class CodebaseReader:
    """Service responsible for reading and grouping source files from the codebase."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def read_files(self, max_files: Optional[int] = None) -> Dict[Path, List[Path]]:
        """
        Scan source files and return them grouped by parent folder.
        
        Returns:
            Dict mapping parent folder Path to a list of file Paths in that folder.
        """
        source_paths = list(iter_source_files(str(self.root_dir)))
        
        if max_files is not None:
            source_paths = source_paths[: max(0, int(max_files))]
        
        logger.info("Found %d source files under %s", len(source_paths), self.root_dir)
        
        return self._group_by_parent_folder(source_paths)

    def read_file_content(self, file_path: Path) -> str:
        """Read a UTF-8 text file with best-effort error handling."""
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Skipping unreadable file %s: %s", file_path, e)
            return ""

    def _group_by_parent_folder(self, files: Iterable[Path]) -> Dict[Path, List[Path]]:
        """Group files by their parent folder."""
        grouped: Dict[Path, List[Path]] = {}
        for file_path in files:
            try:
                parent = file_path.parent
            except Exception:
                continue
            grouped.setdefault(parent, []).append(file_path)

        # Sort files within groups
        for folder in grouped:
            grouped[folder] = sorted(grouped[folder])

        # Return sorted by folder structure for determinism
        return dict(sorted(grouped.items(), key=lambda kv: str(kv[0])))
