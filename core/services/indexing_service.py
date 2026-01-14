import logging
import time
from pathlib import Path
from typing import Optional

from core.ports.graph_port import GraphStore
from core.ports.rag_port import VectorIndex
from core.ports.scan_port import CodebaseScanner

logger = logging.getLogger(__name__)

class IndexingService:
    """Use Case for indexing a codebase directory."""

    def __init__(
        self,
        scanner: CodebaseScanner,
        vector_index: VectorIndex,
        graph_store: GraphStore,
    ):
        self.scanner = scanner
        self.vector_index = vector_index
        self.graph_store = graph_store

    def index_directory(
        self,
        directory: Path,
        project_name: Optional[str] = None,
        include_file_summaries: bool = True
    ) -> str:
        """
        Run the full indexing pipeline on a directory.
        
        Args:
            directory: Directory to index.
            project_name: Optional project identifier.
            include_file_summaries: Whether to generate file-level RAG summaries.
            
        Returns:
            A text summary of the graph build (overview).
        """
        start_time = time.time()
        logger.info("Starting indexing job for %s (project=%s)", directory, project_name)

        # 1. Scan and Parse
        # The scanner implementation currently invokes the parser factory internally.
        # Ideally, parsing would be a separate step, but for now we trust the scanner/parser integration.
        blocks = self.scanner.scan(directory, exclude_tests=True)
        if not blocks:
            logger.warning("No code blocks found in %s", directory)
            return "No code blocks found."

        # Assign project if not set
        if project_name:
            for b in blocks:
                b.project = project_name

        # 2. Vector Indexing
        logger.info("Indexing %d blocks into Vector Store...", len(blocks))
        self.vector_index.index_code_blocks(blocks)
        
        if include_file_summaries:
             logger.info("Indexing file summaries...")
             self.vector_index.index_file_summaries(blocks)
             
        self.vector_index.persist()

        # 3. Graph Building
        logger.info("Rebuilding Project Graph...")
        self.graph_store.rebuild(project=project_name, methods=blocks)
        
        overview = self.graph_store.overview_text(project=project_name)
        
        duration = time.time() - start_time
        logger.info("Indexing completed in %.2fs", duration)
        
        return overview
