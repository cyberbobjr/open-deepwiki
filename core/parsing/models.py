from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CodeBlock:
    """Represents a generic parsed code block (function, method, class, etc.)."""

    id: str
    signature: str
    type: str  # e.g. "method", "function", "class", "constructor"
    language: str  # e.g. "java", "python", "typescript"
    code: str
    calls: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    
    # Context fields
    file_path: Optional[str] = None
    project: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
