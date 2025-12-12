#!/usr/bin/env python3
"""
Java Graph RAG - A Retrieval-Augmented Generation system for Java codebases.

This script implements:
1. Tree-sitter parsing to extract Java method information (ID, signature, type, calls, code, Javadoc)
2. GraphEnrichedRetriever that performs vector search and enriches context with dependency docs
3. Chroma vector store with OpenAI embeddings
4. Mock data, indexing, and test queries
"""

import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Tree-sitter imports
import tree_sitter
from tree_sitter import Language, Parser

# LangChain imports
from langchain.schema import Document
from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.schema.retriever import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun


@dataclass
class JavaMethod:
    """Represents a parsed Java method or constructor."""
    id: str
    signature: str
    type: str  # "method" or "constructor"
    calls: List[str]
    code: str
    javadoc: Optional[str] = None


class JavaParser:
    """Parser for Java code using tree-sitter."""
    
    def __init__(self):
        """Initialize the Java parser with tree-sitter."""
        # Build the Java language
        Language.build_library(
            'build/java-languages.so',
            ['vendor/tree-sitter-java']
        )
        self.java_language = Language('build/java-languages.so', 'java')
        self.parser = Parser()
        self.parser.set_language(self.java_language)
    
    def parse_java_file(self, java_code: str) -> List[JavaMethod]:
        """
        Parse Java code and extract method information.
        
        Args:
            java_code: Java source code as string
            
        Returns:
            List of JavaMethod objects
        """
        tree = self.parser.parse(bytes(java_code, "utf8"))
        methods = []
        
        # Query for methods and constructors
        query = self.java_language.query("""
            (method_declaration) @method
            (constructor_declaration) @constructor
        """)
        
        captures = query.captures(tree.root_node)
        
        for node, capture_name in captures:
            method_type = "method" if capture_name == "method" else "constructor"
            
            # Extract signature
            signature = self._extract_signature(node, java_code)
            
            # Generate ID from signature
            method_id = self._generate_id(signature)
            
            # Extract code
            code = java_code[node.start_byte:node.end_byte]
            
            # Extract method calls
            calls = self._extract_calls(node, java_code)
            
            # Extract Javadoc (sibling node lookup)
            javadoc = self._extract_javadoc(node, java_code)
            
            methods.append(JavaMethod(
                id=method_id,
                signature=signature,
                type=method_type,
                calls=calls,
                code=code,
                javadoc=javadoc
            ))
        
        return methods
    
    def _extract_signature(self, node: tree_sitter.Node, code: str) -> str:
        """Extract method signature from node."""
        # Query for method/constructor components
        signature_parts = []
        
        # Find modifiers, return type, name, and parameters
        for child in node.children:
            if child.type in ['modifiers', 'type_identifier', 'void_type', 'generic_type']:
                signature_parts.append(code[child.start_byte:child.end_byte])
            elif child.type == 'identifier':
                signature_parts.append(code[child.start_byte:child.end_byte])
            elif child.type == 'formal_parameters':
                signature_parts.append(code[child.start_byte:child.end_byte])
        
        return ' '.join(signature_parts).strip()
    
    def _generate_id(self, signature: str) -> str:
        """Generate a unique ID from method signature."""
        # Clean signature and create ID
        cleaned = re.sub(r'\s+', '_', signature)
        cleaned = re.sub(r'[^\w_]', '', cleaned)
        return cleaned.lower()
    
    def _extract_calls(self, node: tree_sitter.Node, code: str) -> List[str]:
        """Extract method calls from node using captures."""
        calls = []
        
        # Query for method invocations
        query = self.java_language.query("""
            (method_invocation
                name: (identifier) @call_name)
        """)
        
        captures = query.captures(node)
        
        for call_node, _ in captures:
            call_name = code[call_node.start_byte:call_node.end_byte]
            calls.append(call_name)
        
        return list(set(calls))  # Remove duplicates
    
    def _extract_javadoc(self, node: tree_sitter.Node, code: str) -> Optional[str]:
        """Extract Javadoc from sibling nodes."""
        # Look for previous sibling that is a comment
        parent = node.parent
        if not parent:
            return None
        
        # Find the node's index in parent's children
        node_index = None
        for i, child in enumerate(parent.children):
            if child.id == node.id:
                node_index = i
                break
        
        if node_index is None or node_index == 0:
            return None
        
        # Check previous sibling
        prev_sibling = parent.children[node_index - 1]
        if prev_sibling.type == 'block_comment':
            comment_text = code[prev_sibling.start_byte:prev_sibling.end_byte]
            # Check if it's a Javadoc comment (starts with /**)
            if comment_text.startswith('/**'):
                return comment_text
        
        return None


class GraphEnrichedRetriever(BaseRetriever):
    """
    LangChain retriever that enriches context with dependency documentation.
    
    Performs vector search, then fetches related docs via "calls" metadata.
    """
    
    vectorstore: Chroma
    k: int = 4
    fetch_k: int = 10
    method_docs_map: Dict[str, Document] = {}
    
    class Config:
        """Configuration for this pydantic object."""
        arbitrary_types_allowed = True
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """
        Retrieve documents relevant to the query with enriched context.
        
        Args:
            query: Search query
            run_manager: Callback manager
            
        Returns:
            List of documents with enriched context
        """
        # Step 1: Perform vector search
        initial_docs = self.vectorstore.similarity_search(query, k=self.k)
        
        # Step 2: Enrich with dependency documentation
        enriched_docs = []
        seen_ids = set()
        
        for doc in initial_docs:
            if doc.metadata.get('id') not in seen_ids:
                enriched_docs.append(doc)
                seen_ids.add(doc.metadata.get('id'))
            
            # Fetch dependencies via "calls" metadata
            calls = doc.metadata.get('calls', [])
            for call_name in calls:
                # Find documents with matching method names
                for method_id, dep_doc in self.method_docs_map.items():
                    if call_name.lower() in dep_doc.metadata.get('signature', '').lower():
                        if method_id not in seen_ids:
                            # Add dependency with context
                            enriched_doc = Document(
                                page_content=f"[DEPENDENCY] {dep_doc.page_content}",
                                metadata={
                                    **dep_doc.metadata,
                                    'is_dependency': True,
                                    'called_from': doc.metadata.get('id')
                                }
                            )
                            enriched_docs.append(enriched_doc)
                            seen_ids.add(method_id)
        
        return enriched_docs


def setup_java_language():
    """Download and setup tree-sitter-java if not already available."""
    import subprocess
    
    # Create vendor directory
    os.makedirs('vendor', exist_ok=True)
    os.makedirs('build', exist_ok=True)
    
    # Clone tree-sitter-java if not exists
    if not os.path.exists('vendor/tree-sitter-java'):
        print("Cloning tree-sitter-java...")
        subprocess.run([
            'git', 'clone',
            'https://github.com/tree-sitter/tree-sitter-java',
            'vendor/tree-sitter-java'
        ], check=True)
    
    # Build language if not exists
    if not os.path.exists('build/java-languages.so'):
        print("Building Java language...")
        Language.build_library(
            'build/java-languages.so',
            ['vendor/tree-sitter-java']
        )


def create_embeddings(base_url: Optional[str] = None) -> OpenAIEmbeddings:
    """
    Create OpenAI embeddings with optional custom internal URL.
    
    Args:
        base_url: Custom OpenAI API base URL (e.g., internal proxy)
        
    Returns:
        Configured OpenAIEmbeddings instance
    """
    if base_url:
        return OpenAIEmbeddings(
            openai_api_base=base_url,
            openai_api_key=os.getenv('OPENAI_API_KEY', 'dummy-key')
        )
    else:
        return OpenAIEmbeddings()


def index_java_methods(
    methods: List[JavaMethod],
    vectorstore: Chroma
) -> Dict[str, Document]:
    """
    Index Java methods into the vector store.
    
    Args:
        methods: List of parsed Java methods
        vectorstore: Chroma vector store
        
    Returns:
        Dictionary mapping method IDs to documents
    """
    documents = []
    method_docs_map = {}
    
    for method in methods:
        # Create document content with all relevant information
        content_parts = [
            f"Signature: {method.signature}",
            f"Type: {method.type}",
        ]
        
        if method.javadoc:
            content_parts.append(f"Documentation: {method.javadoc}")
        
        if method.calls:
            content_parts.append(f"Calls: {', '.join(method.calls)}")
        
        content_parts.append(f"Code:\n{method.code}")
        
        content = "\n\n".join(content_parts)
        
        # Create document with metadata
        doc = Document(
            page_content=content,
            metadata={
                'id': method.id,
                'signature': method.signature,
                'type': method.type,
                'calls': method.calls,
                'has_javadoc': method.javadoc is not None
            }
        )
        
        documents.append(doc)
        method_docs_map[method.id] = doc
    
    # Add to vector store
    vectorstore.add_documents(documents)
    
    return method_docs_map


# Mock Java data for testing
MOCK_JAVA_CODE = """
package com.example.service;

import java.util.List;
import java.util.ArrayList;

/**
 * User service for managing user operations.
 * Handles CRUD operations and user validation.
 */
public class UserService {
    
    private DatabaseConnection db;
    
    /**
     * Creates a new user in the system.
     * 
     * @param username The username for the new user
     * @param email The email address
     * @return The created user ID
     */
    public String createUser(String username, String email) {
        validateEmail(email);
        String userId = generateUserId();
        saveToDatabase(userId, username, email);
        return userId;
    }
    
    /**
     * Validates an email address format.
     * 
     * @param email The email to validate
     * @throws IllegalArgumentException if email is invalid
     */
    private void validateEmail(String email) {
        if (!email.contains("@")) {
            throw new IllegalArgumentException("Invalid email format");
        }
    }
    
    /**
     * Generates a unique user ID.
     * 
     * @return A unique user identifier
     */
    private String generateUserId() {
        return "USER_" + System.currentTimeMillis();
    }
    
    /**
     * Saves user data to the database.
     * 
     * @param userId The user ID
     * @param username The username
     * @param email The email address
     */
    private void saveToDatabase(String userId, String username, String email) {
        db.execute("INSERT INTO users VALUES (?, ?, ?)", userId, username, email);
    }
    
    /**
     * Retrieves all users from the database.
     * 
     * @return List of all users
     */
    public List<User> getAllUsers() {
        return db.query("SELECT * FROM users");
    }
    
    /**
     * Constructs a new UserService.
     * 
     * @param db The database connection
     */
    public UserService(DatabaseConnection db) {
        this.db = db;
        validateConnection(db);
    }
    
    /**
     * Validates the database connection.
     * 
     * @param db The database connection to validate
     */
    private void validateConnection(DatabaseConnection db) {
        if (db == null) {
            throw new IllegalArgumentException("Database connection cannot be null");
        }
    }
}
"""


def main():
    """Main execution function with mock data and test queries."""
    print("=" * 80)
    print("Java Graph RAG - Retrieval-Augmented Generation for Java Code")
    print("=" * 80)
    print()
    
    # Setup tree-sitter Java
    print("Setting up tree-sitter Java parser...")
    try:
        setup_java_language()
        print("✓ Tree-sitter Java setup complete")
    except Exception as e:
        print(f"⚠ Warning: Could not setup tree-sitter-java: {e}")
        print("Continuing with mock mode...")
    print()
    
    # Parse mock Java code
    print("Parsing mock Java code...")
    try:
        parser = JavaParser()
        methods = parser.parse_java_file(MOCK_JAVA_CODE)
        print(f"✓ Parsed {len(methods)} methods/constructors")
        print()
        
        # Display parsed methods
        print("Parsed Methods:")
        print("-" * 80)
        for method in methods:
            print(f"ID: {method.id}")
            print(f"Signature: {method.signature}")
            print(f"Type: {method.type}")
            print(f"Calls: {method.calls}")
            print(f"Has Javadoc: {method.javadoc is not None}")
            print("-" * 80)
        print()
    except Exception as e:
        print(f"⚠ Warning: Could not parse Java code: {e}")
        print("Creating mock methods for demonstration...")
        methods = create_mock_methods()
        print(f"✓ Created {len(methods)} mock methods")
        print()
    
    # Setup embeddings with custom URL
    print("Setting up embeddings...")
    custom_url = os.getenv('OPENAI_API_BASE', None)
    if custom_url:
        print(f"Using custom OpenAI API URL: {custom_url}")
    embeddings = create_embeddings(custom_url)
    print("✓ Embeddings configured")
    print()
    
    # Create Chroma vector store
    print("Creating Chroma vector store...")
    vectorstore = Chroma(
        collection_name="java_methods",
        embedding_function=embeddings,
        persist_directory="./chroma_db"
    )
    print("✓ Vector store created")
    print()
    
    # Index methods
    print("Indexing Java methods...")
    method_docs_map = index_java_methods(methods, vectorstore)
    print(f"✓ Indexed {len(method_docs_map)} methods")
    print()
    
    # Create GraphEnrichedRetriever
    print("Creating GraphEnrichedRetriever...")
    retriever = GraphEnrichedRetriever(
        vectorstore=vectorstore,
        method_docs_map=method_docs_map,
        k=3
    )
    print("✓ Retriever created")
    print()
    
    # Test queries
    print("=" * 80)
    print("Running Test Queries")
    print("=" * 80)
    print()
    
    test_queries = [
        "How do I create a new user?",
        "What validation is performed on user data?",
        "How is the database connection validated?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"Query {i}: {query}")
        print("-" * 80)
        
        results = retriever.get_relevant_documents(query)
        
        print(f"Retrieved {len(results)} documents (including dependencies):")
        for j, doc in enumerate(results, 1):
            is_dep = doc.metadata.get('is_dependency', False)
            doc_type = "[DEPENDENCY]" if is_dep else "[PRIMARY]"
            print(f"\n{doc_type} Document {j}:")
            print(f"Method: {doc.metadata.get('signature', 'N/A')}")
            print(f"Type: {doc.metadata.get('type', 'N/A')}")
            print(f"Calls: {doc.metadata.get('calls', [])}")
            if is_dep:
                print(f"Called from: {doc.metadata.get('called_from', 'N/A')}")
            # Print first 200 chars of content
            content_preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            print(f"Content preview: {content_preview}")
        
        print()
        print("=" * 80)
        print()
    
    print("Demo complete!")


def create_mock_methods() -> List[JavaMethod]:
    """Create mock JavaMethod objects for demonstration when parser is unavailable."""
    return [
        JavaMethod(
            id="public_string_createuser_string_username_string_email",
            signature="public String createUser(String username, String email)",
            type="method",
            calls=["validateEmail", "generateUserId", "saveToDatabase"],
            code="""public String createUser(String username, String email) {
        validateEmail(email);
        String userId = generateUserId();
        saveToDatabase(userId, username, email);
        return userId;
    }""",
            javadoc="/**\n     * Creates a new user in the system.\n     * \n     * @param username The username for the new user\n     * @param email The email address\n     * @return The created user ID\n     */"
        ),
        JavaMethod(
            id="private_void_validateemail_string_email",
            signature="private void validateEmail(String email)",
            type="method",
            calls=[],
            code="""private void validateEmail(String email) {
        if (!email.contains("@")) {
            throw new IllegalArgumentException("Invalid email format");
        }
    }""",
            javadoc="/**\n     * Validates an email address format.\n     * \n     * @param email The email to validate\n     * @throws IllegalArgumentException if email is invalid\n     */"
        ),
        JavaMethod(
            id="private_string_generateuserid",
            signature="private String generateUserId()",
            type="method",
            calls=[],
            code="""private String generateUserId() {
        return "USER_" + System.currentTimeMillis();
    }""",
            javadoc="/**\n     * Generates a unique user ID.\n     * \n     * @return A unique user identifier\n     */"
        ),
        JavaMethod(
            id="private_void_savetodatabase_string_userid_string_username_string_email",
            signature="private void saveToDatabase(String userId, String username, String email)",
            type="method",
            calls=["execute"],
            code="""private void saveToDatabase(String userId, String username, String email) {
        db.execute("INSERT INTO users VALUES (?, ?, ?)", userId, username, email);
    }""",
            javadoc="/**\n     * Saves user data to the database.\n     * \n     * @param userId The user ID\n     * @param username The username\n     * @param email The email address\n     */"
        ),
    ]


if __name__ == "__main__":
    main()
