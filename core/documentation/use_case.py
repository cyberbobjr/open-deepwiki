from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.documentation.semantic_summarizer import SemanticSummarizer
from core.documentation.site_generator import DocumentationSiteGenerator
from core.ports.graph_port import GraphStore
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
    graph_store: Optional[GraphStore] = None


class GenerateDocumentationUseCase:
    """Use Case for generating project documentation."""

    def __init__(
        self,
        reader: CodebaseReader,
        summarizer: SemanticSummarizer,
        site_generator: DocumentationSiteGenerator,
        repository: DocumentationRepository,
        indexer: VectorStoreIndexer,
        graph_store: Optional[GraphStore] = None
    ):
        self.reader = reader
        self.summarizer = summarizer
        self.site_generator = site_generator
        self.repository = repository
        self.indexer = indexer
        self.graph_store = graph_store

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

        if request.progress_callback:
            request.progress_callback("semantic_files", "Analyzing project structure...")
            
        # --- Hybrid Discovery Preparation ---
        
        # A. Get Project Vision (README)
        readme_path = request.root_dir / "README.md"
        project_vision = ""
        if readme_path.exists():
            try:
                raw_readme = readme_path.read_text(encoding="utf-8")
                # Simple HTML/Image strip
                import re
                clean_readme = re.sub(r'<[^>]+>', '', raw_readme)
                clean_readme = re.sub(r'!\[.*?\]\(.*?\)', '', clean_readme)
                project_vision = clean_readme
            except Exception as e:
                logger.warning(f"Failed to read README: {e}")

        # B. Prepare Module Contexts (Raw Text) & Entrypoints
        # We don't have modules yet, but we have folders.
        module_contents: Dict[str, str] = {}
        entrypoint_contents: List[str] = []
        entrypoint_files: List[str] = []
        
        for folder, summaries in file_summaries_by_folder.items():
            try:
                rel = folder.resolve().relative_to(request.root_dir.resolve())
                mod_key = rel.as_posix() or "."
            except Exception:
                mod_key = str(folder)
            
            # Aggregate file summaries for this folder
            joined_files = "\n".join(summaries)
            module_contents[mod_key] = joined_files
            
            # Simple heuristic for entrypoints since we don't have ModuleMetadata yet
            # Looking for "entrypoints", "api", "routers", "cli", "main" in path
            lower_key = mod_key.lower()
            if any(x in lower_key for x in ["entrypoints", "api", "routers", "controllers", "cli", "views"]):
                entrypoint_contents.append(f"Possible Entrypoint Module {mod_key}:\n{joined_files[:3000]}") # Truncate 
                
                # Get files for this folder
                folder_str = str(folder)
                folder_files = [p for p in file_summaries_by_path.keys() if str(Path(p).parent) == folder_str or Path(p).parent == folder]
                entrypoint_files.extend(folder_files)

        # C. Graph Data
        graph_data_summary = ""
        dependencies = {}
        if self.graph_store:
            try:
                graph_data_summary = self.graph_store.overview_text(project=request.project_name)
                dependencies = self.graph_store.get_file_dependencies(project=request.project_name)
            except Exception as e:
                logger.warning(f"Graph retrieval failed: {e}")

        # 2. Detect Features (Hybrid)
        if request.progress_callback:
            request.progress_callback("semantic_features", "Detecting functional features...")
            
        feature_list = self.summarizer.detect_features_hybrid(
            module_contents=module_contents,
            entrypoint_contents=entrypoint_contents,
            project_vision=project_vision,
            graph_data_summary=graph_data_summary,
            max_chars=request.max_context_chars
        )
        
        # 3. Map Files to Features
        mapping = self.summarizer.map_files_to_features(
            file_summaries_by_path, 
            feature_list,
            dependency_graph=dependencies,
            entrypoints=entrypoint_files
        )
        
        # Invert mapping to get Feature -> Modules (for Module Summarization context)
        # And Module -> Features (to pass to summarize_module)
        module_to_features: Dict[str, List[str]] = {}
        feature_to_modules: Dict[str, List[str]] = {}
        
        for feature, fpaths in mapping.items():
            for fp in fpaths:
                try:
                    path_obj = Path(fp)
                    if path_obj.is_absolute():
                        rel_parent = path_obj.parent.relative_to(request.root_dir.resolve())
                    else:
                        rel_parent = path_obj.parent
                    mod_key = rel_parent.as_posix() or "."
                    
                    module_to_features.setdefault(mod_key, []).append(feature)
                    feature_to_modules.setdefault(feature, set()).add(mod_key)
                except Exception:
                    pass
        
        # Deduplicate
        for k in module_to_features:
            module_to_features[k] = sorted(list(set(module_to_features[k])))
        for k in feature_to_modules:
            feature_to_modules[k] = sorted(list(feature_to_modules[k]))


        # 4. Generate Module Summaries (With Feature Context)
        if request.progress_callback:
            request.progress_callback("semantic_modules", "Generating module summaries...")        
        module_summaries: Dict[str, str] = {}
        module_metadata_map: Dict[str, Any] = {} # Actually ModuleMetadata

        for folder, summaries in file_summaries_by_folder.items():
            try:
                rel = folder.resolve().relative_to(request.root_dir.resolve())
                key = rel.as_posix() or "."
            except Exception:
                key = str(folder)
            
            # Fetch related features for this module
            related = module_to_features.get(key, [])
            
            # Now returns ModuleMetadata
            metadata = self.summarizer.summarize_module(
                str(folder),
                summaries,
                related_features=related,
                max_chars=request.max_context_chars
            )
            
            mod_summary = metadata.summary
            module_summaries[key] = mod_summary
            module_metadata_map[key] = metadata

            # Index Module Summary
            if request.index_into_chroma:
                self.indexer.index_module_summary(request.project_name, key, mod_summary)

        # 5. Generate Project Overview
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

        # 6. Site Generation (Feature Pages)
        if request.site_output_dir:
            if request.progress_callback:
                request.progress_callback("site_generation", "Generating feature pages...")
            
            feature_narratives: Dict[str, str] = {}
            feature_deep_dives: Dict[str, Dict[str, str]] = {}
            
            for feature_name, file_paths in list(mapping.items()):
                if not file_paths:
                    continue
                
                feat_summaries = [file_summaries_by_path[p] for p in file_paths if p in file_summaries_by_path]
                
                # Narrative
                narrative = self.summarizer.generate_feature_narrative(
                    feature_name, 
                    feat_summaries,
                    max_chars=request.max_context_chars
                )
                feature_narratives[feature_name] = narrative
                
                # Deep Dives
                feature_deep_dives[feature_name] = {}
                
                # Facet 1: Architecture
                arch_dive = self.summarizer.generate_feature_technical_deep_dive(
                    feature_name,
                    feat_summaries,
                    "ARCHITECTURE_LIFECYCLE",
                    max_chars=request.max_context_chars
                )
                feature_deep_dives[feature_name]["ARCHITECTURE_LIFECYCLE"] = arch_dive
                
                # Facet 2: Data Flow
                data_dive = self.summarizer.generate_feature_technical_deep_dive(
                    feature_name,
                    feat_summaries,
                    "DATA_FLOW_TRANSFORMATIONS",
                    max_chars=request.max_context_chars
                )
                feature_deep_dives[feature_name]["DATA_FLOW_TRANSFORMATIONS"] = data_dive
                
                if request.index_into_chroma:
                    self.indexer.index_feature_page(request.project_name, feature_name, narrative)

            # Build Site (Write to disk)
            if request.progress_callback:
                request.progress_callback("site_generation", "Building static site...")
                
            self.site_generator.build_site(
                output_dir=request.site_output_dir,
                project_overview=overview,
                module_summaries=module_summaries,
                feature_narratives=feature_narratives,
                feature_deep_dives=feature_deep_dives,
                feature_map=mapping,
                module_metadata=module_metadata_map,
                feature_to_modules=feature_to_modules
            )

        return request.output_path
