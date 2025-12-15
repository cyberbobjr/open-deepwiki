#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProjectGraphStore(unittest.TestCase):
    def test_rebuild_overview_and_neighbors(self):
        from core.parsing.java_parser import JavaMethod
        from core.project_graph import SqliteProjectGraphStore

        methods = [
            JavaMethod(
                id="a",
                signature="public void a()",
                type="method",
                calls=["b"],
                code="void a(){b();}",
                file_path="src/A.java",
                project="demo",
            ),
            JavaMethod(
                id="b",
                signature="public void b()",
                type="method",
                calls=[],
                code="void b(){}",
                file_path="src/B.java",
                project="demo",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "graph.sqlite3")
            store = SqliteProjectGraphStore(sqlite_path=db_path)
            stats = store.rebuild(project="demo", methods=methods)

            self.assertEqual(stats.files, 2)
            self.assertEqual(stats.methods, 2)
            self.assertGreaterEqual(stats.contains_edges, 2)

            overview = store.overview_text(project="demo", limit=10)
            self.assertIn("Project: demo", overview)
            self.assertIn("Files indexed:", overview)
            self.assertIn("Methods indexed:", overview)

            # neighbors expects a stored node_id (scoped)
            neigh = store.neighbors_text(project="demo", node_id="demo::a", depth=1, limit=20)
            self.assertIn("Calls:", neigh)


class TestProjectOverviewIndexing(unittest.TestCase):
    def test_index_project_overview_writes_doc(self):
        from core.rag.indexing import index_project_overview
        from langchain_chroma import Chroma
        from langchain_core.embeddings import DeterministicFakeEmbedding

        with tempfile.TemporaryDirectory() as tmp:
            vectorstore = Chroma(
                collection_name="test_project_overview",
                embedding_function=DeterministicFakeEmbedding(size=12),
                persist_directory=tmp,
            )

            doc = index_project_overview(
                project="demo",
                overview_text="Project: demo\nFiles indexed: 1",
                vectorstore=vectorstore,
            )

            self.assertEqual(doc.metadata.get("doc_type"), "project_overview")
            self.assertEqual(doc.metadata.get("project"), "demo")
            self.assertEqual(doc.metadata.get("scoped_id"), "demo::project::overview")

            # Verify retrievable via filtered similarity search.
            results = vectorstore.similarity_search(
                "Project: demo",
                k=5,
                filter={
                    "$and": [
                        {"doc_type": "project_overview"},
                        {"project": "demo"},
                    ]
                },
            )
            self.assertTrue(results)
            self.assertEqual(results[0].metadata.get("doc_type"), "project_overview")


if __name__ == "__main__":
    unittest.main()
