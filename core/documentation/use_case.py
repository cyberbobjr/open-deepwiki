from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.documentation.semantic_summarizer import SemanticSummarizer
from core.documentation.site_generator import DocumentationSiteGenerator
from core.ports.storage_port import DocumentationRepository, VectorStoreIndexer
from core.services.codebase_reader import CodebaseReader


@dataclass
class DocumentationRequest:
    """Request object for documentation generation."""
    root_dir: Path
    output_path: Path
    site_output_dir: Optional[Path] = None
    index_into_chroma: bool = False
    project_name: Optional[str] = None
    max_files: Optional[int] = None
    precomputed_summaries: Optional[Dict[str, str]] = None
    max_context_chars: int = 400_000
    batch_size: int = 10
    progress_callback: Optional[Callable[[str, str], None]] = None
    indexed_at: Optional[str] = None
    indexed_path: Optional[str] = None


class GenerateDocumentationUseCase:
    """Use Case for generating project documentation."""

    def __init__(
        self,
        reader: CodebaseReader,
        summarizer: SemanticSummarizer,
        site_generator: DocumentationSiteGenerator,
        repository: DocumentationRepository,
        indexer: VectorStoreIndexer
    ):
        self.reader = reader
        self.summarizer = summarizer
        self.site_generator = site_generator
        self.repository = repository
        self.indexer = indexer

    def execute(self, request: DocumentationRequest) -> Path:
        """
        Execute the documentation generation pipeline.
        
        Args:
            request: Configuration for the documentation job.
            
        Returns:
            Path to the generated project overview.
        """
        
        # 1. Gather file summaries
        file_summaries_by_path: Dict[str, str] = {}
        file_summaries_by_folder: Dict[Path, List[str]] = {}

        if request.precomputed_summaries:
            file_summaries_by_path = request.precomputed_summaries
            # Reconstruct folder grouping from paths
            for fpath, summary in file_summaries_by_path.items():
                parent = Path(fpath).parent
                file_summaries_by_folder.setdefault(parent, []).append(summary)
        else:
            # Scan and summarize
            grouped_files = self.reader.read_files(max_files=request.max_files)
            
            # Flatten files for smart resolution
            all_files = [f for files in grouped_files.values() for f in files]
            self.summarizer.set_known_files(all_files)
            
            for folder, files in grouped_files.items():
                summaries: List[str] = []
                for file_path in files:
                    code = self.reader.read_file_content(file_path)
                    summary = self.summarizer.summarize_file(
                        file_path, 
                        code, 
                        max_chars=request.max_context_chars
                    )
                    summaries.append(summary)
                    file_summaries_by_path[str(file_path)] = summary
                
                if request.progress_callback:
                    request.progress_callback("semantic_files", f"Processed folder {folder.name}")
                    
                file_summaries_by_folder[folder] = summaries

        # 2. Generate Module Summaries
        if request.progress_callback:
            request.progress_callback("semantic_modules", "Generating module summaries...")        
        module_summaries: Dict[str, str] = {}
        module_metadata_map: Dict[str, Any] = {} # Actually ModuleMetadata, but loose type for now

        for folder, summaries in file_summaries_by_folder.items():
            try:
                rel = folder.resolve().relative_to(request.root_dir.resolve())
                key = rel.as_posix() or "."
            except Exception:
                key = str(folder)
            
            # Now returns ModuleMetadata
            metadata = self.summarizer.summarize_module(
                str(folder),
                summaries,
                max_chars=request.max_context_chars
            )
            
            mod_summary = metadata.summary
            module_summaries[key] = mod_summary
            module_metadata_map[key] = metadata

            # Index Module Summary
            if request.index_into_chroma:
                self.indexer.index_module_summary(request.project_name, key, mod_summary)

        # 3. Generate Project Overview
        if request.progress_callback:
            request.progress_callback("semantic_overview", "Generating project overview...")
        overview = self.summarizer.create_project_overview(
            request.root_dir,
            module_summaries,
            max_chars=request.max_context_chars
        )
        
        # Index Project Overview
        if request.index_into_chroma:
            self.indexer.index_overview(
                request.project_name, 
                overview,
                indexed_path=request.indexed_path,
                indexed_at=request.indexed_at
            )

        self.repository.save_project_overview(overview)

        # 4. Feature Extraction & Site Generation
        if request.site_output_dir:
            if request.progress_callback:
                request.progress_callback("site_generation", "Extracting features...")
            
            # Extract features from MODULE summaries
            feature_list = self.summarizer.extract_features_from_modules(module_summaries)
            
            # Map files to features
            mapping = self.summarizer.map_files_to_features(file_summaries_by_path, feature_list)
            
            # Generate pages for each feature
            feature_pages: Dict[str, str] = {}
            feature_to_modules: Dict[str, List[str]] = {}

            if request.progress_callback:
                request.progress_callback("site_generation", "Generating feature pages...")
                
            for feature_name, file_paths in list(mapping.items()):
                if not file_paths:
                    if feature_name in mapping:
                        del mapping[feature_name]
                    continue
                
                # Calculate related modules for this feature
                related_modules = set()
                for fp in file_paths:
                    try:
                        # Reconstruct module key logic same as above
                        # key = rel path of parent
                        path_obj = Path(fp)
                        if path_obj.is_absolute():
                            rel_parent = path_obj.parent.relative_to(request.root_dir.resolve())
                        else:
                            # Fallback if path is already relative or just a name? 
                            # file_summaries_by_path keys are absolute from reader
                            rel_parent = path_obj.parent
                        
                        mod_key = rel_parent.as_posix() or "."
                        related_modules.add(mod_key)
                    except Exception:
                        pass
                feature_to_modules[feature_name] = list(related_modules)

                feat_summaries = [file_summaries_by_path[p] for p in file_paths if p in file_summaries_by_path]
                page_content = self.summarizer.generate_feature_page(
                    feature_name, 
                    feat_summaries,
                    max_chars=request.max_context_chars
                )
                feature_pages[feature_name] = page_content
                
                if request.index_into_chroma:
                    self.indexer.index_feature_page(request.project_name, feature_name, page_content)

            # Build Site (Write to disk)
            if request.progress_callback:
                request.progress_callback("site_generation", "Building static site...")
                
            self.site_generator.build_site(
                output_dir=request.site_output_dir,
                project_overview=overview,
                module_summaries=module_summaries,
                feature_pages=feature_pages,
                feature_map=mapping,
                module_metadata=module_metadata_map,
                feature_to_modules=feature_to_modules
            )

        return request.output_path
