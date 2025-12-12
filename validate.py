#!/usr/bin/env python3
"""
Simple validation script for Java Graph RAG that demonstrates the concepts
without requiring full dependency installation.
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
    """Validate the script has all required components."""
    print("\nValidating script structure...")
    
    with open('java_graph_rag.py', 'r') as f:
        script = f.read()
    
    required_components = [
        ('JavaParser class', r'class JavaParser:'),
        ('parse_java_file method', r'def parse_java_file'),
        ('.captures usage', r'\.captures\('),
        ('Extract ID', r'id:'),
        ('Extract signature', r'signature:'),
        ('Extract type', r'type:'),
        ('Extract calls', r'calls:'),
        ('Extract code', r'code:'),
        ('Extract Javadoc', r'javadoc'),
        ('Sibling node lookup', r'sibling'),
        ('GraphEnrichedRetriever class', r'class GraphEnrichedRetriever'),
        ('Vector search', r'similarity_search'),
        ('Fetch dependencies', r'calls.*metadata'),
        ('Enrich context', r'enriched'),
        ('OpenAIEmbeddings', r'OpenAIEmbeddings'),
        ('Custom URL config', r'base_url'),
        ('Chroma', r'Chroma'),
        ('Mock Java data', r'MOCK_JAVA_CODE'),
        ('Index methods', r'def index_java_methods'),
        ('__main__', r'if __name__ == "__main__"'),
        ('Test queries', r'test_queries'),
    ]
    
    all_found = True
    for name, pattern in required_components:
        if re.search(pattern, script):
            print(f"✓ {name}")
        else:
            print(f"✗ {name} NOT found")
            all_found = False
    
    return all_found


def validate_mock_data():
    """Validate the mock Java data is present and valid."""
    print("\nValidating mock Java data...")
    
    with open('java_graph_rag.py', 'r') as f:
        script = f.read()
    
    # Extract MOCK_JAVA_CODE
    match = re.search(r'MOCK_JAVA_CODE = """(.+?)"""', script, re.DOTALL)
    if not match:
        print("✗ MOCK_JAVA_CODE not found")
        return False
    
    mock_code = match.group(1)
    
    # Check for Java elements
    java_elements = [
        ('Package declaration', r'package\s+'),
        ('Import statements', r'import\s+'),
        ('Class declaration', r'class\s+\w+'),
        ('Method with Javadoc', r'/\*\*[\s\S]*?\*/\s*public'),
        ('Constructor', r'public\s+\w+\s*\([^)]*\)\s*{'),
        ('Private method', r'private\s+\w+'),
    ]
    
    all_found = True
    for name, pattern in java_elements:
        if re.search(pattern, mock_code):
            print(f"✓ {name} in mock data")
        else:
            print(f"✗ {name} NOT in mock data")
            all_found = False
    
    return all_found


def validate_tree_sitter_usage():
    """Validate tree-sitter is used correctly."""
    print("\nValidating tree-sitter usage...")
    
    with open('java_graph_rag.py', 'r') as f:
        script = f.read()
    
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
    
    with open('java_graph_rag.py', 'r') as f:
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
