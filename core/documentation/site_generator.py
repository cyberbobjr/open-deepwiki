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
        feature_pages: Dict[str, str],
        feature_map: Dict[str, List[str]],
        module_metadata: Dict[str, Any] = None, # Dict[str, ModuleMetadata]
        feature_to_modules: Dict[str, List[str]] = None,
    ) -> List[Path]:
        """
        Write all documentation artifacts to disk and generate index/sitemap.
        
        Args:
            output_dir: Target directory for the site.
            project_overview: Content of the main project overview.
            module_summaries: Dictionary of {module_name: content}.
            feature_pages: Dictionary of {feature_name: content}.
            feature_map: Dictionary of {feature_name: [file_paths]}.
            module_metadata: Dictionary of {module_name: ModuleMetadata}.
            feature_to_modules: Dictionary of {feature_name: [module_names]}.
            
        Returns:
            List of generated file paths.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        features_dir = output_dir / "features"
        modules_dir = output_dir / "modules"
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
                # Remove bold/italic
                text_clean = re.sub(r'[*_]{2,}', '', text_raw)
                text_clean = re.sub(r'[*_]', '', text_clean)
                # Remove links [text](url) -> text
                text_clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text_clean)
                # Remove inline code `code`
                text_clean = re.sub(r'`([^`]+)`', r'\1', text_clean)
                text_clean = text_clean.strip()
                
                # Generate slug from clean text
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
                    # Strip markdown from description too if needed, but keeping it raw is OK for now
                    return l
            return ""

        # Data structure for TOC (Hierarchical)
        toc_data = {
            "overview": None,
            "categories": {}, # { CategoryName: [ {title, path, short_title, headings...} ] }
            "features": [],
            "feature_navigation": {} # { feature_name: { related_modules: [...] } }
        }

        # 1. Write Project Overview
        overview_path = output_dir / "PROJECT_OVERVIEW.md"
        
        # Ensure # Title is present if missing
        overview_content = (project_overview or "").strip()
        if not overview_content.startswith("#"):
             # It likely has logic inside to add title, but just in case
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
            
            rel_path = f"modules/{fname}"
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

        # 3. Write Feature Pages
        feature_paths_rel: Dict[str, str] = {}
        for feature_name, content in sorted(feature_pages.items()):
            fname = self.feature_filename(feature_name)
            path = features_dir / fname
            final_content = (content or "").strip() + "\n"
            path.write_text(final_content, encoding="utf-8")
            
            rel_path = f"features/{fname}"
            feature_paths_rel[feature_name] = rel_path
            generated_files.append(path)

            toc_data["features"].append({
                "title": feature_name,
                "path": rel_path,
                "headings": _extract_headings(final_content)
            })
            
            # 4. Feature Navigation
            # Use feature_to_modules to populate detailed info
            related_modules_info = []
            if feature_to_modules and feature_name in feature_to_modules:
                mod_keys = feature_to_modules[feature_name]
                for mk in mod_keys:
                    if mk in module_info_map:
                        related_modules_info.append(module_info_map[mk])
                    else:
                        # Fallback for unknown/implicit modules
                        related_modules_info.append({
                            "title": mk, 
                            "short_title": mk, 
                            "path": "", 
                            "category": "Unknown"
                        })
            
            # Sort by category then title
            related_modules_info.sort(key=lambda x: (x.get("category", ""), x.get("title", "")))

            toc_data["feature_navigation"][feature_name] = {
                "description_short": _extract_short_description(final_content),
                "related_modules": related_modules_info
            }


        # 4. Generate Index / Sitemap
        index_lines = []
        index_lines.append("# Documentation\n")
        
        index_lines.append("## Global Overview")
        index_lines.append(f"See [Project Overview](PROJECT_OVERVIEW.md)\n")

        index_lines.append("## Modules")
        for cat, mods in toc_data["categories"].items():
             index_lines.append(f"### {cat}")
             for m in mods:
                 index_lines.append(f"- [{m['short_title']}]({m['path']})")
        
        index_lines.append("\n## Features")
        for feat_name in sorted(feature_paths_rel.keys()):
            rel_path = feature_paths_rel[feat_name]
            index_lines.append(f"- [{feat_name}]({rel_path})")

        index_path = output_dir / "index.md"
        index_path.write_text("\n".join(index_lines), encoding="utf-8")
        generated_files.append(index_path)

        # 5. Generate JSON Sitemap (Legacy? Keeping it for now if needed, but TOC is better)
        sitemap = {
            "overview": "PROJECT_OVERVIEW.md",
            "modules": [{"name": k, "path": v} for k, v in sorted(module_paths.items())],
            "features": [{"name": k, "path": v} for k, v in sorted(feature_paths_rel.items())],
        }
        (output_dir / "sitemap.json").write_text(json.dumps(sitemap, indent=2), encoding="utf-8")

        # 6. Generate JSON TOC (The new requested file)
        (output_dir / "toc.json").write_text(json.dumps(toc_data, indent=2), encoding="utf-8")
        generated_files.append(output_dir / "toc.json")

        return generated_files
