#!/usr/bin/env python3
"""Unit tests for Java Graph RAG."""

import os
import sys
import tempfile
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestJavaParsingAndAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from core.parsing.tree_sitter_setup import setup_java_language

            setup_java_language()
        except Exception as e:
            raise unittest.SkipTest(
                f"tree-sitter-java setup failed (git/build tools missing?): {e}"
            )

    def _read_fixture(self) -> str:
        fixture_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fixtures",
            "SampleService.java",
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_parses_methods_constructors_and_javadoc(self):
        from core.parsing.java_parser import JavaParser

        code = self._read_fixture()
        parser = JavaParser()
        methods = parser.parse_java_file(code)

        signatures = [m.signature for m in methods]
        self.assertTrue(any("createUser" in s for s in signatures))
        self.assertTrue(any("validateEmail" in s for s in signatures))
        self.assertTrue(any("SampleService" in s for s in signatures))

        create_user = next(m for m in methods if "createUser" in m.signature)
        self.assertEqual(create_user.type, "method")
        self.assertIn("validateEmail", create_user.calls)
        self.assertIn("generateUserId", create_user.calls)
        self.assertIn("saveToDatabase", create_user.calls)
        self.assertIsNotNone(create_user.javadoc)
        self.assertTrue((create_user.javadoc or "").strip().startswith("/**"))

        constructor = next(
            m for m in methods if m.type == "constructor" and "SampleService" in m.signature
        )
        self.assertIsNotNone(constructor.javadoc)
        self.assertIn("validateConnection", constructor.calls)

    def test_indexing_builds_documents_and_metadata(self):
        from core.parsing.java_parser import JavaParser
        from core.rag.indexing import index_java_methods
        from langchain_core.embeddings import DeterministicFakeEmbedding
        from langchain_chroma import Chroma

        code = self._read_fixture()
        parser = JavaParser()
        methods = parser.parse_java_file(code)

        with tempfile.TemporaryDirectory() as tmp:
            vectorstore = Chroma(
                collection_name="test_java_methods",
                embedding_function=DeterministicFakeEmbedding(size=12),
                persist_directory=tmp,
            )
            method_docs_map = index_java_methods(methods, vectorstore)

        self.assertEqual(set(method_docs_map.keys()), set(m.id for m in methods))

        create_user = next(m for m in methods if "createUser" in m.signature)
        doc = method_docs_map[create_user.id]
        self.assertEqual(doc.metadata["id"], create_user.id)
        self.assertIn("createUser", doc.metadata["signature"])
        self.assertIn("validateEmail", doc.metadata["calls"])
        self.assertTrue(doc.metadata["has_javadoc"])
        self.assertIn("Signature:", doc.page_content)
        self.assertIn("Calls:", doc.page_content)
        self.assertIn("Code:", doc.page_content)

    def test_graph_enrichment_adds_dependency_docs(self):
        from core.parsing.java_parser import JavaParser
        from core.rag.indexing import index_java_methods
        from core.rag.retriever import GraphEnrichedRetriever
        from langchain_core.embeddings import DeterministicFakeEmbedding
        from langchain_chroma import Chroma

        code = self._read_fixture()
        parser = JavaParser()
        methods = parser.parse_java_file(code)

        with tempfile.TemporaryDirectory() as tmp:
            vectorstore = Chroma(
                collection_name="test_java_methods_enrich",
                embedding_function=DeterministicFakeEmbedding(size=12),
                persist_directory=tmp,
            )
            method_docs_map = index_java_methods(methods, vectorstore)

            create_user = next(m for m in methods if "createUser" in m.signature)
            primary_doc = method_docs_map[create_user.id]

            # Make the initial retrieval deterministic for the test.
            vectorstore.similarity_search = lambda query, k=4, filter=None, **kwargs: [primary_doc]

            retriever = GraphEnrichedRetriever(
                vectorstore=vectorstore,
                method_docs_map=method_docs_map,
                k=1,
            )

            results = retriever.get_relevant_documents("create a user")
            self.assertGreaterEqual(len(results), 2)

            dep_docs = [d for d in results if d.metadata.get("is_dependency")]
            self.assertTrue(dep_docs, "Expected at least one dependency document")

            dep = dep_docs[0]
            self.assertEqual(dep.metadata.get("called_from"), create_user.id)
            self.assertTrue(dep.page_content.startswith("[DEPENDENCY]"))

    def test_scan_java_codebase_dir_collects_methods(self):
        from core.parsing.java_parser import JavaParser
        from api.indexer import scan_java_methods

        parser = JavaParser()
        methods = scan_java_methods("./fixtures", parser)

        self.assertTrue(methods)
        signatures = [m.signature for m in methods]
        self.assertTrue(any("createUser" in s for s in signatures))


if __name__ == "__main__":
    unittest.main()
