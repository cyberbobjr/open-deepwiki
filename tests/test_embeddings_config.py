import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEmbeddingsConfig(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "OPENAI_EMBEDDING_API_BASE": os.environ.get("OPENAI_EMBEDDING_API_BASE"),
            "OPENAI_EMBEDDING_MODEL": os.environ.get("OPENAI_EMBEDDING_MODEL"),
            "OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH": os.environ.get(
                "OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH"
            ),
        }
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["OPENAI_EMBEDDING_API_BASE"] = "http://example.invalid/v1"
        os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        os.environ.pop("OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH", None)

    def tearDown(self) -> None:
        for k in list(self._orig.keys()):
            os.environ.pop(k, None)
        for k, v in self._orig.items():
            if v is not None:
                os.environ[k] = v

    def test_default_disables_ctx_length_tokenization(self):
        from core.rag.embeddings import create_embeddings

        emb = create_embeddings()
        self.assertFalse(getattr(emb, "check_embedding_ctx_length"))

    def test_env_can_enable_ctx_length_tokenization(self):
        from core.rag.embeddings import create_embeddings

        os.environ["OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH"] = "true"
        emb = create_embeddings()
        self.assertTrue(getattr(emb, "check_embedding_ctx_length"))
