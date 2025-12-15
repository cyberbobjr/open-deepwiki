#!/usr/bin/env python3
"""Unit tests for Java Graph RAG."""

import os
import sys
import tempfile
import time
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
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
        from indexer import scan_java_methods

        parser = JavaParser()
        fixtures_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "fixtures",
        )
        methods = scan_java_methods(fixtures_path, parser)

        self.assertTrue(methods)
        signatures = [m.signature for m in methods]
        self.assertTrue(any("createUser" in s for s in signatures))

    def test_generate_missing_javadoc_edits_file_and_writes_log(self):
        from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class FakeLLM:
            def invoke(self, messages):
                # Always return a minimal valid JavaDoc.
                return _Resp(
                    "/**\n * Auto-generated.\n *\n * @return value\n */"
                )

        java_source = (
            "package demo;\n\n"
            "public class A {\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            log_dir = os.path.join(tmp, "logs")
            summary = generate_missing_javadoc_in_directory(
                root,
                log_dir=log_dir,
                llm=FakeLLM(),
            )

            self.assertEqual(summary["files_scanned"], 1)
            self.assertEqual(summary["files_modified"], 1)
            # Class + method should be documented (verifies class parsing in generator).
            self.assertEqual(summary["members_documented"], 2)
            self.assertTrue(os.path.exists(summary["log_file"]))

            with open(path, "r", encoding="utf-8") as f:
                updated = f.read()
            self.assertIn("/**", updated)
            self.assertIn("Auto-generated", updated)

            # Ensure the class doc is inserted before the class declaration.
            self.assertLess(updated.find("/**"), updated.find("public class A"))

    def test_generate_javadoc_skips_existing_full_docs(self):
        from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class FakeLLM:
            def invoke(self, messages):
                return _Resp(
                    "/**\n * NEW DOC line 1\n * NEW DOC line 2\n * NEW DOC line 3\n */"
                )

        java_source = (
            "package demo;\n\n"
            "/**\n"
            " * Existing class documentation.\n"
            " * More details.\n"
            " * Even more details.\n"
            " */\n"
            "public class A {\n"
            "    /**\n"
            "     * Existing method documentation.\n"
            "     * More details.\n"
            "     * Even more details.\n"
            "     */\n"
            "    public int keep(int a) {\n"
            "        return a;\n"
            "    }\n\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            log_dir = os.path.join(tmp, "logs")
            summary = generate_missing_javadoc_in_directory(
                root,
                log_dir=log_dir,
                llm=FakeLLM(),
            )

            # Only the missing method JavaDoc should be generated.
            self.assertEqual(summary["members_documented"], 1)

            with open(path, "r", encoding="utf-8") as f:
                updated = f.read()
            self.assertEqual(updated.count("Existing class documentation."), 1)
            self.assertEqual(updated.count("Existing method documentation."), 1)
            self.assertIn("NEW DOC line 1", updated)

    def test_generate_javadoc_replaces_short_docs(self):
        from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class FakeLLM:
            def invoke(self, messages):
                return _Resp(
                    "/**\n * Improved doc line 1\n * Improved doc line 2\n * Improved doc line 3\n */"
                )

        java_source = (
            "package demo;\n\n"
            "/**\n"
            " * Existing class documentation.\n"
            " * More details.\n"
            " * Even more details.\n"
            " */\n"
            "public class A {\n"
            "    /**\n"
            "     * TODO\n"
            "     */\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            log_dir = os.path.join(tmp, "logs")
            summary = generate_missing_javadoc_in_directory(
                root,
                log_dir=log_dir,
                llm=FakeLLM(),
            )

            # The short method JavaDoc should be replaced.
            self.assertEqual(summary["members_documented"], 1)

            with open(path, "r", encoding="utf-8") as f:
                updated = f.read()
            self.assertNotIn("TODO", updated)
            self.assertIn("Improved doc line 1", updated)
            # Still only two blocks: class + method.
            self.assertEqual(updated.count("/**"), 2)

    def test_generate_javadoc_min_meaningful_lines_is_configurable(self):
        from core.documentation.javadoc_generator import generate_missing_javadoc_in_directory

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class FakeLLM:
            def invoke(self, messages):
                return _Resp(
                    "/**\n * Improved doc line 1\n * Improved doc line 2\n * Improved doc line 3\n */"
                )

        # Existing method JavaDoc has exactly 1 meaningful line ("TODO").
        java_source = (
            "package demo;\n\n"
            "public class A {\n"
            "    /**\n"
            "     * TODO\n"
            "     */\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            log_dir = os.path.join(tmp, "logs")

            # With min_meaningful_lines=1, a 1-line JavaDoc is NOT considered short.
            summary = generate_missing_javadoc_in_directory(
                root,
                log_dir=log_dir,
                llm=FakeLLM(),
                min_meaningful_lines=1,
            )
            self.assertEqual(summary["members_documented"], 1)  # class only

            with open(path, "r", encoding="utf-8") as f:
                updated = f.read()
            # Class was missing JavaDoc, so it should get the generated block.
            self.assertIn("Improved doc line 1", updated)
            self.assertLess(updated.find("Improved doc line 1"), updated.find("public class A"))

            # Method already had a 1-line JavaDoc and min_meaningful_lines=1, so it should NOT be replaced.
            self.assertIn("TODO", updated)
            self.assertLess(updated.find("TODO"), updated.find("public int add"))


class TestJavadocJobManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from core.parsing.tree_sitter_setup import setup_java_language

            setup_java_language()
        except Exception as e:
            raise unittest.SkipTest(
                f"tree-sitter-java setup failed (git/build tools missing?): {e}"
            )

    def test_job_manager_prevents_overlapping_jobs(self):
        from core.documentation.javadoc_job_manager import JavadocJobManager

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class SlowLLM:
            def invoke(self, messages):
                time.sleep(0.25)
                return _Resp(
                    "/**\n * Job doc line 1\n * Job doc line 2\n * Job doc line 3\n */"
                )

        java_source = (
            "package demo;\n\n"
            "public class A {\n"
            "    public int a0() { return 0; }\n"
            "    public int a1() { return 1; }\n"
            "    public int a2() { return 2; }\n"
            "    public int a3() { return 3; }\n"
            "    public int a4() { return 4; }\n"
            "    public int a5() { return 5; }\n"
            "    public int a6() { return 6; }\n"
            "    public int a7() { return 7; }\n"
            "}\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            mgr = JavadocJobManager()
            job = mgr.start(root, llm=SlowLLM())

            with self.assertRaises(RuntimeError):
                mgr.start(root, llm=SlowLLM())

            # Cleanup: request stop and wait for completion.
            mgr.stop(job.job_id)
            deadline = time.time() + 10
            while time.time() < deadline:
                status = next(j for j in mgr.list() if j.job_id == job.job_id).status
                if status != "running":
                    break
                time.sleep(0.05)
            self.assertNotEqual(
                next(j for j in mgr.list() if j.job_id == job.job_id).status,
                "running",
            )

    def test_job_manager_can_stop_job(self):
        from core.documentation.javadoc_job_manager import JavadocJobManager

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        class SlowLLM:
            def invoke(self, messages):
                time.sleep(0.05)
                return _Resp(
                    "/**\n * Job doc line 1\n * Job doc line 2\n * Job doc line 3\n */"
                )

        # Enough members to give us time to stop mid-run.
        methods = "\n".join([f"    public int m{i}() {{ return {i}; }}" for i in range(60)])
        java_source = "\n".join([
            "package demo;",
            "",
            "public class A {",
            methods,
            "}",
            "",
        ])

        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "src")
            os.makedirs(root, exist_ok=True)
            path = os.path.join(root, "A.java")
            with open(path, "w", encoding="utf-8") as f:
                f.write(java_source)

            mgr = JavadocJobManager()
            job = mgr.start(root, llm=SlowLLM())
            time.sleep(0.15)
            mgr.stop(job.job_id)

            deadline = time.time() + 10
            while time.time() < deadline:
                status = next(j for j in mgr.list() if j.job_id == job.job_id).status
                if status != "running":
                    break
                time.sleep(0.05)

            final = next(j for j in mgr.list() if j.job_id == job.job_id)
            self.assertEqual(final.status, "stopped")


if __name__ == "__main__":
    unittest.main()
