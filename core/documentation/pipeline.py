from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from config import AppConfig
from core.documentation.semantic_summarizer import SemanticSummarizer
from core.documentation.site_generator import DocumentationSiteGenerator
from core.documentation.use_case import (DocumentationRequest,
                                         GenerateDocumentationUseCase)
from core.ports.graph_port import GraphStore
from core.ports.llm_port import LLMProvider
from core.ports.storage_port import DocumentationRepository, VectorStoreIndexer
from core.rag.embeddings import create_embeddings
from core.rag.indexing import (index_feature_page, index_module_summary,
                               index_project_overview)
from core.services.codebase_reader import CodebaseReader
from utils.chat import create_chat_model

logger = logging.getLogger(__name__)


class LangChainLLMAdapter(LLMProvider):
    """Adapter for LangChain Chat Models."""
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def invoke(self, messages: Sequence[BaseMessage]) -> str:
        response = self.llm.invoke(messages)
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        return str(content)

    def invoke_with_tools(self, messages: Sequence[BaseMessage], tools: Sequence[Any]) -> BaseMessage:
        llm_with_tools = self.llm.bind_tools(tools)
        return llm_with_tools.invoke(messages)

    def invoke_structured(self, messages: Sequence[BaseMessage], model_class: Any) -> Any:
        structured_llm = self.llm.with_structured_output(model_class)
        return structured_llm.invoke(messages)


class FileSystemRepository(DocumentationRepository):
    """Adapter for saving documentation to the local filesystem."""
    def __init__(self, output_path: Path, site_output_dir: Optional[Path]):
        self.output_path = output_path
        self.site_output_dir = site_output_dir

    def save_project_overview(self, content: str) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(content, encoding="utf-8")
        logger.info("Wrote project overview to %s", self.output_path)

    def save_feature_page(self, feature_name: str, filename: str, content: str) -> None:
        if not self.site_output_dir:
            return
        
        features_dir = self.site_output_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        path = features_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.debug("Wrote feature page '%s' to %s", feature_name, path)

    def save_index_page(self, content: str) -> None:
        if not self.site_output_dir:
            return
            
        (self.site_output_dir / "index.md").write_text(content, encoding="utf-8")
        logger.info("Wrote site index to %s", self.site_output_dir / "index.md")


class ChromaIndexerAdapter(VectorStoreIndexer):
    """Adapter for indexing into ChromaDB."""
    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "code_blocks"):
        base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
        embeddings = create_embeddings(base_url)
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

    def index_overview(
        self,
        project_name: str,
        content: str,
        indexed_path: Optional[str] = None,
        indexed_at: Optional[str] = None
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
             # In a real app we might raise, but here we log/warn as per original behavior check
             raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

        index_project_overview(
            project=project_name, 
            overview_text=content, 
            vectorstore=self.vectorstore,
            indexed_path=indexed_path,
            indexed_at=indexed_at
        )
        
        # Note: persisting is automatic in newer Chroma versions
        logger.info("Indexed project overview into Chroma (project=%s)", project_name)

    def index_feature_page(self, project: str, feature: str, content: str) -> None:
        if not os.getenv("OPENAI_API_KEY"):
             raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

        index_feature_page(
            project=project,
            feature_name=feature,
            page_content=content,
            vectorstore=self.vectorstore
        )

    def index_module_summary(self, project: str, module_name: str, content: str) -> None:
        if not os.getenv("OPENAI_API_KEY"):
             raise RuntimeError("OPENAI_API_KEY is not set; indexing requires embeddings.")

        index_module_summary(
            project=project,
            module_name=module_name,
            summary_content=content,
            vectorstore=self.vectorstore
        )


class NoOpIndexer(VectorStoreIndexer):
    """Null object for when indexing is disabled."""
    def index_overview(
        self,
        project_name: str,
        content: str,
        indexed_path: Optional[str] = None,
        indexed_at: Optional[str] = None
    ) -> None:
        pass

    def index_feature_page(self, project: str, feature: str, content: str) -> None:
        pass

    def index_module_summary(self, project: str, module_name: str, content: str) -> None:
        pass


def run_documentation_pipeline(
    *,
    root_dir: Path,
    config: AppConfig,
    output_path: Path,
    site_output_dir: Optional[Path],
    index_into_chroma: bool,
    max_files: Optional[int],
    precomputed_file_summaries: Optional[Dict[str, str]] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    indexed_at: Optional[str] = None,
    indexed_path: Optional[str] = None,
    project_name: Optional[str] = None,
    graph_store: Optional[GraphStore] = None,
) -> Path:
    """Generate a DeepWiki-style project overview markdown file.

    This function mimics the 'High Quality' documentation pipeline:
    1. Scan source files (if summaries not provided).
    2. Generate file-level semantic summaries using LLM (if not provided).
    3. Generate module-level summaries using LLM.
    4. Generate project overview using LLM.
    5. Optionally generate a static site.
    6. Optionally index the overview.
    """
    repo_adapter = FileSystemRepository(output_path, site_output_dir)
    
    if index_into_chroma:
        indexer_adapter = ChromaIndexerAdapter(
            persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
            collection_name=os.getenv("CHROMA_COLLECTION", "code_blocks")
        )
    else:
        indexer_adapter = NoOpIndexer()
        
    # Create dedicated Chat Model for summarization   
    sum_api_key = os.getenv("OPEN_DEEPWIKI_SUMMARIZATION_API_KEY") 
    sum_llm = create_chat_model(
        model=os.getenv("OPEN_DEEPWIKI_SUMMARIZATION_MODEL") or os.getenv("OPENAI_CHAT_MODEL"),
        base_url=os.getenv("OPEN_DEEPWIKI_SUMMARIZATION_API_BASE") or os.getenv("OPENAI_CHAT_API_BASE"),
        api_key=sum_api_key
    )
    summarizer_adapter = LangChainLLMAdapter(sum_llm)
    
    reader = CodebaseReader(root_dir)
    summarizer = SemanticSummarizer(summarizer_adapter, reader)
    
    max_ctx = int(getattr(config, "llm_max_context_chars", 400_000))
    batch_sz = int(getattr(config, "docs_feature_batch_size", 10))
    
    site_generator = DocumentationSiteGenerator()
    
    use_case = GenerateDocumentationUseCase(
        reader=reader,
        summarizer=summarizer,
        site_generator=site_generator,
        repository=repo_adapter,
        indexer=indexer_adapter,
        graph_store=graph_store
    )
    
    final_project_name = project_name or getattr(config, "project_name", None) or os.getenv("OPEN_DEEPWIKI_PROJECT")
    
    request = DocumentationRequest(
        root_dir=root_dir,
        output_path=output_path,
        site_output_dir=site_output_dir,
        index_into_chroma=index_into_chroma,
        project_name=final_project_name,
        max_files=max_files,
        precomputed_summaries=precomputed_file_summaries,
        max_context_chars=max_ctx,
        batch_size=batch_sz,

        progress_callback=progress_callback,
        indexed_at=indexed_at,
        indexed_path=indexed_path,
        graph_store=graph_store,
    )
    
    return use_case.execute(request)
