#!/usr/bin/env python3
"""Validation script for open-deepwiki core modules.

This repo originally had a single `java_graph_rag.py` demo script.
The implementation is now split into small modules (parser/indexing/retriever/etc).

This script is intentionally lightweight: it validates the presence of the core
building blocks without requiring a full runtime setup.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class JavaMethod:
    """Represents a parsed Java method or constructor."""
    id: str
    signature: str
    type: str  # "method" or "constructor"
    calls: List[str]
    code: str
    javadoc: Optional[str] = None


def validate_requirements():
    """Validate the requirements are properly specified."""
    print("Validating requirements...")
    
    with open('requirements.txt', 'r') as f:
        requirements = f.read()
    
    required = [
        'tree-sitter==0.21.3',
        'langchain',
        'chromadb',
        'openai',
        'tiktoken'
    ]
    
    for req in required:
        if req in requirements:
            print(f"✓ {req} found in requirements.txt")
        else:
            print(f"✗ {req} NOT found in requirements.txt")
            return False
    
    return True


def validate_script_structure():
    """Validate the codebase has all required components."""
    print("\nValidating module structure...")

    targets = {
        "java_parser.py": "core/parsing/java_parser.py",
        "tree_sitter_setup.py": "core/parsing/tree_sitter_setup.py",
        "rag_retriever.py": "core/rag/retriever.py",
        "rag_indexing.py": "core/rag/indexing.py",
        "rag_embeddings.py": "core/rag/embeddings.py",
    }

    sources = {}
    for label, path in targets.items():
        with open(path, "r", encoding="utf-8") as f:
            sources[label] = f.read()

    required_components = [
        ("JavaParser class", "java_parser.py", r"class JavaParser"),
        ("parse_java_file method", "java_parser.py", r"def parse_java_file"),
        (".captures usage", "java_parser.py", r"\.captures\("),
        ("Javadoc extraction", "java_parser.py", r"def _extract_javadoc"),
        ("GraphEnrichedRetriever class", "rag_retriever.py", r"class GraphEnrichedRetriever"),
        ("Vector search", "rag_retriever.py", r"similarity_search"),
        ("calls parsing (str/list)", "rag_retriever.py", r"isinstance\(calls_meta, str\)"),
        ("Index methods", "rag_indexing.py", r"def index_java_methods"),
        ("calls serialized", "rag_indexing.py", r"calls_serialized"),
        ("Create embeddings", "rag_embeddings.py", r"def create_embeddings"),
        ("Custom URL config", "rag_embeddings.py", r"base_url"),
        ("tree-sitter build", "tree_sitter_setup.py", r"Language\.build_library"),
    ]
    
    all_found = True
    for name, file_key, pattern in required_components:
        if re.search(pattern, sources[file_key]):
            print(f"✓ {name} ({file_key})")
        else:
            print(f"✗ {name} NOT found ({file_key})")
            all_found = False
    
    return all_found


def validate_mock_data():
    """Legacy hook: mock data demo script was removed."""
    print("\nValidating mock Java data...")
    print("(skipped) Demo script removed; fixtures cover parsing instead.")
    return True


def validate_tree_sitter_usage():
    """Validate tree-sitter is used correctly."""
    print("\nValidating tree-sitter usage...")

    # Tree-sitter est maintenant réparti :
    # - build du langage dans `tree_sitter_setup.py`
    # - parser + query + `.captures()` dans `java_parser.py`
    with open("core/parsing/tree_sitter_setup.py", "r", encoding="utf-8") as f:
        setup_src = f.read()
    with open("core/parsing/java_parser.py", "r", encoding="utf-8") as f:
        parser_src = f.read()

    script = setup_src + "\n" + parser_src
    
    checks = [
        ('tree-sitter import', r'import tree_sitter'),
        ('Language.build_library', r'Language\.build_library'),
        ('Parser creation', r'Parser\(\)'),
        ('set_language', r'set_language'),
        ('parse method', r'\.parse\('),
        ('query creation', r'\.query\('),
        ('.captures call', r'\.captures\('),
        ('tree-sitter-java', r'tree-sitter-java'),
    ]
    
    all_found = True
    for name, pattern in checks:
        if re.search(pattern, script):
            print(f"✓ {name}")
        else:
            print(f"✗ {name} NOT found")
            all_found = False
    
    return all_found


def validate_langchain_retriever():
    """Validate the GraphEnrichedRetriever implementation."""
    print("\nValidating GraphEnrichedRetriever...")

    with open("core/rag/retriever.py", "r", encoding="utf-8") as f:
        script = f.read()
    
    checks = [
        ('BaseRetriever inheritance', r'class GraphEnrichedRetriever\(BaseRetriever\)'),
        ('vectorstore attribute', r'vectorstore:'),
        ('method_docs_map attribute', r'method_docs_map:'),
        ('_get_relevant_documents', r'def _get_relevant_documents'),
        ('Vector search step', r'similarity_search'),
        ('Dependency fetching', r'calls.*metadata'),
        ('Enrichment logic', r'enriched'),
        ('Document creation', r'Document\('),
        ('Metadata handling', r'metadata'),
    ]
    
    all_found = True
    for name, pattern in checks:
        if re.search(pattern, script):
            print(f"✓ {name}")
        else:
            print(f"✗ {name} NOT found")
            all_found = False
    
    return all_found


def main():
    """Run all validations."""
    print("=" * 80)
    print("Java Graph RAG - Validation Script")
    print("=" * 80)
    print()
    
    validations = [
        validate_requirements,
        validate_script_structure,
        validate_mock_data,
        validate_tree_sitter_usage,
        validate_langchain_retriever,
    ]
    
    all_passed = True
    for validation in validations:
        try:
            if not validation():
                all_passed = False
        except Exception as e:
            print(f"\n✗ Validation failed with exception: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    print()
    print("=" * 80)
    if all_passed:
        print("✓ All validations passed!")
        print("The Java Graph RAG script is properly implemented.")
    else:
        print("✗ Some validations failed")
        print("Please review the issues above.")
    print("=" * 80)
    
    return all_passed


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
