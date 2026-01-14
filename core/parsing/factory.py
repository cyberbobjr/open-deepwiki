from __future__ import annotations

from typing import Dict, List, Optional, Type

from core.parsing.base import BaseParser
from core.parsing.impl.java_parser import JavaParser
from core.parsing.impl.python_parser import PythonParser
from core.parsing.impl.typescript_parser import TypeScriptParser


class ParserFactory:
    """Factory to instantiate the correct parser for a given file."""

    _parsers: Dict[str, Type[BaseParser]] = {
        ".java": JavaParser,
        ".py": PythonParser,
        ".ts": TypeScriptParser,
        ".tsx": TypeScriptParser,
    }

    _instances: Dict[Type[BaseParser], BaseParser] = {}

    @classmethod
    def get_parser(cls, file_path: str) -> Optional[BaseParser]:
        """Return an instantiated parser suitable for the file path (cached)."""
        # Simple extension-based dispatch for now
        import os
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        parser_cls = cls._parsers.get(ext)
        if parser_cls:
            if parser_cls not in cls._instances:
                cls._instances[parser_cls] = parser_cls()
            return cls._instances[parser_cls]
        
        return None
    
    @classmethod
    def register_parser(cls, extension: str, parser_cls: Type[BaseParser]) -> None:
        """Register a new parser for an extension."""
        cls._parsers[extension.lower()] = parser_cls

    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """Return a list of supported file extensions (e.g. ['.java', '.py'])."""
        return list(cls._parsers.keys())
