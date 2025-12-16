import os
import sys
import unittest
from unittest import mock

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
            "OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS": os.environ.get(
                "OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS"
            ),
            "OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING": os.environ.get(
                "OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING"
            ),
        }
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["OPENAI_EMBEDDING_API_BASE"] = "http://example.invalid/v1"
        os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        os.environ.pop("OPEN_DEEPWIKI_EMBEDDINGS_CHECK_CTX_LENGTH", None)
        os.environ.pop("OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS", None)
        os.environ.pop("OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING", None)

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

    def test_max_input_tokens_truncates_before_embedding(self):
        """Ensures we truncate locally and do not send overly long inputs."""

        from core.rag.embeddings import create_embeddings

        # Use a deterministic encoding; "hello" is 1 token in cl100k_base.
        os.environ["OPEN_DEEPWIKI_EMBEDDINGS_MAX_INPUT_TOKENS"] = "3"
        os.environ["OPEN_DEEPWIKI_EMBEDDINGS_TOKEN_ENCODING"] = "cl100k_base"

        emb = create_embeddings()

        captured = {}

        def _fake_embed_documents(self, texts):  # type: ignore[no-untyped-def]
            captured["texts"] = list(texts)
            return [[0.0, 0.0, 0.0] for _ in texts]

        with mock.patch(
            "langchain_openai.OpenAIEmbeddings.embed_documents",
            new=_fake_embed_documents,
        ):
            emb.embed_documents(["hello hello hello hello hello"])

        # After truncation to 3 tokens, we should not have all 5 words.
        self.assertIn("texts", captured)
        self.assertEqual(len(captured["texts"]), 1)
        self.assertNotEqual(captured["texts"][0], "hello hello hello hello hello")
