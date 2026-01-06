import logging
from pathlib import Path
from typing import List, Optional

# We try to import LangChain's splitter. 
# If not available (though it should be), we fallback or error out.
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    # Use standard langchain import if older version
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class GenericAppParser:
    """Parser for generic resource files (YAML, JSON, XML, MD, etc.).
    
    Treats files as plain text and chunks them using a recursive character splitter.
    """

    def parse_file(self, file_path: Path, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
        """Parse a single file into chunks.

        Args:
            file_path: Absolute path to the file.
            chunk_size: Maximum tokens per chunk.
            chunk_overlap: Overlap between chunks (default 200).

        Returns:
            List of LangChain Documents.
        """
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                # Fallback to latin-1 if utf-8 fails
                text = file_path.read_text(encoding="latin-1")
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                return []
        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return []

        if not text.strip():
            return []

        # Use tiktoken encoder for accurately respecting token limits if possible,
        # otherwise default length function (characters).
        # We assume cl100k_base (OpenAI) as default encoding usually.
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            encoding_name="cl100k_base" 
        )
        
        chunks = splitter.split_text(text)
        
        docs = []
        for i, chunk in enumerate(chunks):
            # Create a Document
            # Metadata will be enriched by the indexer/service later (project, etc.)
            doc = Document(
                page_content=chunk,
                metadata={
                    "source": str(file_path),
                    "filename": file_path.name,
                    "extension": file_path.suffix.lower(),
                    "chunk_index": i,
                }
            )
            docs.append(doc)
            
        return docs
