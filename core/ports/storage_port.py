from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class DocumentationRepository(ABC):
    """Abstract interface for saving documentation artifacts."""

    @abstractmethod
    def save_project_overview(self, content: str) -> None:
        """Save the project overview markdown."""
        pass

    @abstractmethod
    def save_feature_page(self, feature_name: str, filename: str, content: str) -> None:
        """Save a feature documentation page."""
        pass
        
    @abstractmethod
    def save_index_page(self, content: str) -> None:
        """Save the main index page."""
        pass


class VectorStoreIndexer(ABC):
    """Abstract interface for indexing content into a vector store."""

    @abstractmethod
    def index_overview(self, project_name: str, content: str, indexed_path: Optional[str] = None, indexed_at: Optional[str] = None) -> None:
        """Index the project overview into the vector store."""
        pass

    @abstractmethod
    def index_feature_page(self, project: str, feature: str, content: str) -> None:
        """Index a feature page into the vector store."""
        pass

    @abstractmethod
    def index_module_summary(self, project: str, module_name: str, content: str) -> None:
        """Index a module summary into the vector store."""
        pass
