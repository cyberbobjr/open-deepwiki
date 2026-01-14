from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.parsing.models import CodeBlock


class BaseParser(ABC):
    """Abstract base class for language-specific parsers."""

    @abstractmethod
    def parse_file(self, code: str, *, file_path: Optional[str] = None) -> List[CodeBlock]:
        """Parse source code content and return extracted code blocks."""
        pass
