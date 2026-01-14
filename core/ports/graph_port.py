from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence

from core.parsing.models import CodeBlock


@dataclass(frozen=True)
class GraphStats:
    project: Optional[str]
    files: int
    methods: int
    call_edges: int
    contains_edges: int

class GraphStore(ABC):
    """Interface for storing and retrieving project graph data."""

    @abstractmethod
    def rebuild(self, *, project: Optional[str], methods: Sequence[CodeBlock]) -> GraphStats:
        """Rebuild the graph for a given project scope."""
        pass

    @abstractmethod
    def overview_text(self, *, project: Optional[str], limit: int = 25) -> str:
        """Get a text overview of the graph."""
        pass

    @abstractmethod
    def neighbors_text(self, *, project: Optional[str], node_id: str, depth: int = 1, limit: int = 60) -> str:
        """Get text description of neighbors for a node."""
        pass
