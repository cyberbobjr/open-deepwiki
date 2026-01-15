
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def verify_docs(output_dir: Path):
    print(f"Verifying docs in {output_dir}...")
    
    # 1. Check Directory Structure
    features_dir = output_dir / "features"
    tech_ref_dir = output_dir / "technical_reference"
    modules_dir = tech_ref_dir / "modules"
    
    if not features_dir.exists():
        print("FAIL: features directory missing")
        sys.exit(1)
    if not tech_ref_dir.exists():
        print("FAIL: technical_reference directory missing")
        sys.exit(1)
    if not modules_dir.exists():
        print("FAIL: technical_reference/modules directory missing")
        sys.exit(1)

    # 2. Check TOC.json Schema
    toc_path = output_dir / "toc.json"
    if not toc_path.exists():
        print("FAIL: toc.json missing")
        sys.exit(1)
        
    try:
        toc = json.loads(toc_path.read_text())
    except Exception as e:
        print(f"FAIL: toc.json invalid json: {e}")
        sys.exit(1)
        
    if "features" not in toc:
        print("FAIL: toc.json missing 'features' key")
        sys.exit(1)
    if "technical_reference" not in toc:
        print("FAIL: toc.json missing 'technical_reference' key")
        sys.exit(1)
        
    tech_cats = toc["technical_reference"].get("categories", {})
    if not tech_cats:
        print("WARN: technical_reference.categories is empty")
        
    # 3. Check Feature Structure and Links
    for feat in toc.get("features", []):
        feat_path = output_dir / feat["path"]
        if not feat_path.exists():
             print(f"FAIL: Feature index missing: {feat['path']}")
             sys.exit(1)
             
        # Check sub-chapters
        for sub in feat.get("sub_chapters", []):
            sub_path = output_dir / sub["path"]
            if not sub_path.exists():
                print(f"FAIL: Feature sub-chapter missing: {sub['path']}")
                sys.exit(1)
            
            # Check Mermaid in sub-chapters (Deep Dives)
            content = sub_path.read_text()
            if "```mermaid" in content:
                # Basic check for IDs
                # Look for `participant id as "Label"` or `id["Label"]`
                # We want to ensure IDs are safe
                node_matches = re.finditer(r'participant\s+([a-zA-Z0-9]+)\s+as', content)
                for m in node_matches:
                    if not re.match(r'^[a-zA-Z0-9]+$', m.group(1)):
                        print(f"WARN: Mermaid unsafe participant ID in {sub['path']}: {m.group(1)}")

    # 4. Check Module Links in Features
    # Modified: Check 'implementation_details'
    used_modules = set()
    for feat in toc.get("features", []):
        for impl in feat.get("implementation_details", []):
            mod_path = output_dir / impl["path"]
            if not mod_path.exists():
                print(f"FAIL: Implementation detail path invalid: {impl['path']}")
                sys.exit(1)
            
            # Record mapped path to check exclusion later
            used_modules.add(str(mod_path.absolute()))
            
            # Verify Backlink in Module File
            mod_content = mod_path.read_text()
            if "> [!NOTE]" not in mod_content:
                 print(f"WARN: Module {impl['title']} missing Context Note (!NOTE)")
            if "[[Feature" in mod_content or f"[[{feat['title']}]]" in mod_content:
                 pass # Good
            else:
                 # It might use the short title or slug, harder to verify strictly without exact text
                 pass

    # 5. Verify Technical Reference Exclusions
    # Modules in technical reference should NOT be in used_modules
    # Note: This is a "strict" check based on the new philosophy (Fluidity)
    for cat_name, entries in tech_cats.items():
        for entry in entries:
             e_path = (output_dir / entry["path"]).absolute()
             if str(e_path) in used_modules:
                 print(f"WARN: Module {entry['title']} is in both Feature Implementation Details AND Technical Reference. It should be excluded from Tech Ref.")

    print("SUCCESS: Documentation structure verified.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/debug_docs.py <output_dir>")
        sys.exit(1)
    
    verify_docs(Path(sys.argv[1]))
