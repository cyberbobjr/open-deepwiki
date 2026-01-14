from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from core.parsing.models import CodeBlock


class VectorIndex(ABC):
    """Interface for indexing code artifacts into a vector store."""

    @abstractmethod
    def index_code_blocks(self, methods: List[CodeBlock]) -> int:
        """
        Index code blocks.
        Returns: Number of blocks indexed.
        """
        pass

    @abstractmethod
    def index_file_summaries(self, methods: List[CodeBlock]) -> int:
        """
        Index file-level summaries computed from blocks.
        Returns: Number of summaries indexed.
        """
        pass
        
    @abstractmethod
    def persist(self) -> None:
        """Persist changes to storage."""
        pass

class Retriever(ABC):
    """Interface for retrieving documents."""
    
    @abstractmethod
    def query(self, query: str, k: int = 5, **kwargs: Any) -> List[Any]:
        """Retrieve relevant documents."""
        pass
