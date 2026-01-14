from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Protocol

from core.parsing.models import CodeBlock


class ScanProgressCallback(Protocol):
    def __call__(self, current: int, total: int, message: Optional[str]) -> None: ...

class CodebaseScanner(ABC):
    """Interface for scanning a codebase for source files."""

    @abstractmethod
    def scan(
        self, 
        root_dir: Path, 
        exclude_tests: bool = True,
        progress_callback: Optional[ScanProgressCallback] = None
    ) -> List[CodeBlock]:
        """Scan and parse code blocks from the codebase."""
        pass
        
    @abstractmethod
    def iter_files(self, root_dir: Path, exclude_tests: bool = True) -> Iterable[Path]:
        """Yield source files found in the codebase."""
        pass
