from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def _slugify_feature_name(name: str) -> str:
    """Convert a feature name into a safe filename slug."""
    s = (name or "").strip().lower()
    # Remove markdown links, bold, code ticks
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s) # links
    s = re.sub(r"[*_`]", "", s) # formatting
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "feature"


class DocumentationSiteGenerator:
    """Generate a feature-based documentation site on disk (Pure I/O)."""

    def __init__(self) -> None:
        pass

    def feature_filename(self, feature_name: str) -> str:
        return f"{_slugify_feature_name(feature_name)}.md"


    def build_site(
        self,
        output_dir: Path,
        project_overview: str,
        module_summaries: Dict[str, str],
        feature_narratives: Dict[str, str],
        feature_deep_dives: Dict[str, Dict[str, str]] = None,
        feature_map: Dict[str, List[str]] = None,
        module_metadata: Dict[str, Any] = None, 
        feature_to_modules: Dict[str, List[str]] = None,
    ) -> List[Path]:
        """
        Write all documentation artifacts to disk and generate index/sitemap.
        
        Args:
            output_dir: Target directory for the site.
            project_overview: Content of the main project overview.
            module_summaries: Dictionary of {module_name: content}.
            feature_narratives: Dictionary of {feature_name: narrative_content}.
            feature_deep_dives: Dictionary of {feature_name: {facet_slug: content}}.
            feature_map: Dictionary of {feature_name: [file_paths]}.
            module_metadata: Dictionary of {module_name: ModuleMetadata}.
            feature_to_modules: Dictionary of {feature_name: [module_names]}.
            
        Returns:
            List of generated file paths.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        features_dir = output_dir / "features"
        # Technical Reference directory
        tech_ref_dir = output_dir / "technical_reference"
        modules_dir = tech_ref_dir / "modules"
        
        features_dir.mkdir(parents=True, exist_ok=True)
        modules_dir.mkdir(parents=True, exist_ok=True)
        
        generated_files: List[Path] = []
        
        # Helper to collect headings unique per file
        def _extract_headings(md_content: str) -> List[Dict[str, Any]]:
            headings = []
            seen_slugs: Dict[str, int] = {}
            
            for match in re.finditer(r'^(#{1,3})\s+(.+)$', md_content, re.MULTILINE):
                level = len(match.group(1))
                text_raw = match.group(2).strip()
                
                # Strip markdown for the text display
                text_clean = text_raw
                # Remove images
                text_clean = re.sub(r'!\[.*?\]\(.*?\)', '', text_clean)
                # Remove links [text](url) -> text
                text_clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text_clean)
                # Remove bold/italic/strikethrough/code
                text_clean = re.sub(r'[*_~`]', '', text_clean)
                text_clean = text_clean.strip()
                
                # Generate slug from clean text
                # We want robust slugs: alphanumeric dashed
                slug = text_clean.lower()
                slug = re.sub(r'[^\w\s-]', '', slug)
                slug = re.sub(r'[\s]+', '-', slug)
                
                # Handle duplicates
                if slug in seen_slugs:
                    seen_slugs[slug] += 1
                    slug = f"{slug}-{seen_slugs[slug]}"
                else:
                    seen_slugs[slug] = 0
                    
                headings.append({
                    "level": level, 
                    "text": text_clean,
                    "slug": slug
                })
            return headings
        
        def _extract_short_description(content: str) -> str:
            # Simple heuristic: first non-heading, non-empty line
            lines = content.splitlines()
            for line in lines:
                l = line.strip()
                if l and not l.startswith('#') and not l.startswith('`'):
                    return l
            return ""

        # Data structure for TOC (Hierarchical)
        toc_data = {
            "overview": None,
            "categories": {}, # { CategoryName: [ {title, path, short_title, headings...} ] }
            "features": [],
            "technical_reference": { "categories": {} },
            # "feature_navigation" is removed from final public TOC logic usually, but we keep structure
        }

        # 1. Write Project Overview
        overview_path = output_dir / "PROJECT_OVERVIEW.md"
        
        # Ensure # Title is present if missing
        overview_content = (project_overview or "").strip()
        if not overview_content.startswith("#"):
             pass
        overview_content += "\n"
        
        overview_path.write_text(overview_content, encoding="utf-8")
        generated_files.append(overview_path)

        toc_data["overview"] = {
            "title": "Project Overview",
            "path": "PROJECT_OVERVIEW.md",
            "headings": _extract_headings(overview_content)
        }

        # 2. Write Module Summaries
        module_paths: Dict[str, str] = {}
        # We need a map of module_name -> module info for the feature nav lookup later
        module_info_map: Dict[str, Any] = {} 

        for mod_name, content in sorted(module_summaries.items()):
            slug = _slugify_feature_name(mod_name)
            fname = f"{slug}.md"
            path = modules_dir / fname
            final_content = (content or "").strip() + "\n"
            path.write_text(final_content, encoding="utf-8")
            
            rel_path = f"technical_reference/modules/{fname}"
            module_paths[mod_name] = rel_path
            generated_files.append(path)
            
            # Extract Metadata
            metadata = module_metadata.get(mod_name) if module_metadata else None
            short_title = getattr(metadata, "short_title", mod_name) if metadata else mod_name
            category = getattr(metadata, "category", "Uncategorized") if metadata else "Modules"
            
            entry = {
                "title": mod_name,
                "short_title": short_title, 
                "path": rel_path,
                "headings": _extract_headings(final_content)
            }
            
            module_info_map[mod_name] = {
                "title": mod_name,
                "short_title": short_title,
                "path": rel_path,
                "category": category
            }
            
            if category not in toc_data["categories"]:
                toc_data["categories"][category] = []
            toc_data["categories"][category].append(entry)

        # 3. Write Feature Pages (Hierarchical)
        feature_paths_map: Dict[str, str] = {} # feature_name -> relative path to index
        
        for feature_name, narrative_content in sorted(feature_narratives.items()):
            feature_slug = _slugify_feature_name(feature_name)
            feature_folder = features_dir / feature_slug
            feature_folder.mkdir(parents=True, exist_ok=True)
            
            # 3.1 Write Narrative (index.md)
            index_path = feature_folder / "index.md"
            final_content = (narrative_content or "").strip() + "\n"
            index_path.write_text(final_content, encoding="utf-8")
            generated_files.append(index_path)
            
            rel_index_path = f"features/{feature_slug}/index.md"
            feature_paths_map[feature_name] = rel_index_path
            
            sub_chapters = []
            
            # 3.2 Write Deep Dives
            dives = (feature_deep_dives or {}).get(feature_name, {})
            
            # Map known facets to standard filenames
            facet_filename_map = {
                "ARCHITECTURE_LIFECYCLE": "architecture.md",
                "DATA_FLOW_TRANSFORMATIONS": "data-flow.md"
            }
            facet_title_map = {
                "ARCHITECTURE_LIFECYCLE": "Architecture & Lifecycle",
                "DATA_FLOW_TRANSFORMATIONS": "Data Flow"
            }

            for facet_type, dive_content in dives.items():
                fname = facet_filename_map.get(facet_type, f"{_slugify_feature_name(facet_type)}.md")
                dive_path = feature_folder / fname
                final_dive = (dive_content or "").strip() + "\n"
                dive_path.write_text(final_dive, encoding="utf-8")
                generated_files.append(dive_path)
                
                sub_chapters.append({
                    "title": facet_title_map.get(facet_type, facet_type.replace("_", " ").title()),
                    "path": f"features/{feature_slug}/{fname}"
                })
            
            # 3.3 Collect Related Modules (Implementation Details)
            related_modules_entries = []
            if feature_to_modules and feature_name in feature_to_modules:
                mod_keys = feature_to_modules[feature_name]
                for mk in mod_keys:
                    if mk in module_info_map:
                        related_modules_entries.append({
                            "title": module_info_map[mk]["short_title"],
                            "path": module_info_map[mk]["path"]
                        })
            
            toc_data["features"].append({
                "title": feature_name,
                "path": rel_index_path,
                "sub_chapters": sub_chapters,
                "implementation_details": related_modules_entries
            })

        # 4. Technical Reference (Modules) - REMOVED
        # toc_data["technical_reference"] = { "categories": {} }
        
        # We pop 'categories' as it was just an intermediate bucket for modules.
        # Since we are removing technical_reference, we just discard these orphaned modules from the TOC.
        # They are still generated on disk but not reachable via sidebar unless linked.
        toc_data.pop("categories", {})

        # Cleanup temp keys
        if "feature_navigation" in toc_data:
            del toc_data["feature_navigation"]

        # 5. Generate Index.md (Landing Page)
        index_lines = []
        index_lines.append("# Documentation\n")
        index_lines.append("## Global Overview")
        index_lines.append(f"See [Project Overview](PROJECT_OVERVIEW.md)\n")
        
        index_lines.append("## Features")
        for feat in toc_data["features"]:
             index_lines.append(f"- [{feat['title']}]({feat['path']})")
             for sub in feat["sub_chapters"]:
                 index_lines.append(f"  - [{sub['title']}]({sub['path']})")
             if feat.get("implementation_details"):
                 index_lines.append(f"  - Technical Components:")
                 for imp in feat["implementation_details"]:
                      index_lines.append(f"    - [{imp['title']}]({imp['path']})")

        # Technical Reference section removed from index.md as well
        # if toc_data["technical_reference"]["categories"]:
        #     index_lines.append("\n## Technical Reference (Other Modules)")
        #     for cat, mods in toc_data["technical_reference"]["categories"].items():
        #          index_lines.append(f"### {cat}")
        #          for m in mods:
        #              index_lines.append(f"- [{m['short_title']}]({m['path']})")

        index_path = output_dir / "index.md"
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        generated_files.append(index_path)

        # 6. Generate JSON TOC
        (output_dir / "toc.json").write_text(json.dumps(toc_data, indent=2), encoding="utf-8")
        generated_files.append(output_dir / "toc.json")
        
        # Remove legacy sitemap if exists
        legacy_sitemap = output_dir / "sitemap.json"
        if legacy_sitemap.exists():
            legacy_sitemap.unlink()

        return generated_files
