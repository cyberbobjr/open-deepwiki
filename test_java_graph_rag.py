#!/usr/bin/env python3
"""
Test script for Java Graph RAG - validates core parsing functionality.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required imports work."""
    print("Testing imports...")
    
    try:
        from tree_sitter import Language, Parser
        print("✓ tree-sitter imports successful")
    except ImportError as e:
        print(f"✗ Failed to import tree-sitter: {e}")
        return False
    
    try:
        from java_graph_rag import JavaMethod, create_mock_methods
        print("✓ JavaMethod and mock methods imported")
    except ImportError as e:
        print(f"✗ Failed to import from java_graph_rag: {e}")
        return False
    
    return True


def test_mock_methods():
    """Test mock method generation."""
    print("\nTesting mock method generation...")
    
    from java_graph_rag import create_mock_methods
    
    methods = create_mock_methods()
    print(f"✓ Created {len(methods)} mock methods")
    
    # Verify structure
    for method in methods:
        assert hasattr(method, 'id'), "Method missing 'id' attribute"
        assert hasattr(method, 'signature'), "Method missing 'signature' attribute"
        assert hasattr(method, 'type'), "Method missing 'type' attribute"
        assert hasattr(method, 'calls'), "Method missing 'calls' attribute"
        assert hasattr(method, 'code'), "Method missing 'code' attribute"
        assert hasattr(method, 'javadoc'), "Method missing 'javadoc' attribute"
    
    print("✓ All mock methods have required attributes")
    
    # Test specific method
    create_user = methods[0]
    assert create_user.type == "method"
    assert "createUser" in create_user.signature
    assert "validateEmail" in create_user.calls
    assert "generateUserId" in create_user.calls
    assert "saveToDatabase" in create_user.calls
    print("✓ Mock method structure validated")
    
    return True


def test_java_method_dataclass():
    """Test JavaMethod dataclass."""
    print("\nTesting JavaMethod dataclass...")
    
    from java_graph_rag import JavaMethod
    
    method = JavaMethod(
        id="test_method",
        signature="public void testMethod()",
        type="method",
        calls=["helperMethod"],
        code="public void testMethod() { helperMethod(); }",
        javadoc="/** Test method */"
    )
    
    assert method.id == "test_method"
    assert method.signature == "public void testMethod()"
    assert method.type == "method"
    assert method.calls == ["helperMethod"]
    assert "helperMethod" in method.code
    assert method.javadoc == "/** Test method */"
    
    print("✓ JavaMethod dataclass works correctly")
    return True


def test_tree_sitter_setup():
    """Test tree-sitter basic functionality."""
    print("\nTesting tree-sitter basic functionality...")
    
    from tree_sitter import Language, Parser
    
    # This will fail if tree-sitter-java isn't set up, but that's expected
    # We're just testing that the API works
    try:
        parser = Parser()
        print("✓ Parser created successfully")
    except Exception as e:
        print(f"✗ Failed to create parser: {e}")
        return False
    
    return True


def main():
    """Run all tests."""
    print("=" * 80)
    print("Java Graph RAG - Test Suite")
    print("=" * 80)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Mock Methods", test_mock_methods),
        ("JavaMethod Dataclass", test_java_method_dataclass),
        ("Tree-sitter Setup", test_tree_sitter_setup),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n✗ {name} test failed")
        except Exception as e:
            failed += 1
            print(f"\n✗ {name} test failed with exception: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 80)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
