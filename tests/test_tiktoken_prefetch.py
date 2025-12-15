import os
import sys
import types
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTiktokenPrefetch(unittest.TestCase):
    def test_prefetch_disabled_does_nothing(self):
        from config import AppConfig, prefetch_tiktoken_encodings

        calls = []
        fake = types.SimpleNamespace(get_encoding=lambda name: calls.append(name))

        # Even if tiktoken exists, the function should return early.
        orig = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = fake
        try:
            prefetch_tiktoken_encodings(AppConfig(tiktoken_prefetch=False))
        finally:
            if orig is None:
                sys.modules.pop("tiktoken", None)
            else:
                sys.modules["tiktoken"] = orig

        self.assertEqual(calls, [])

    def test_prefetch_defaults_to_cl100k_base(self):
        from config import AppConfig, prefetch_tiktoken_encodings

        calls = []
        fake = types.SimpleNamespace(get_encoding=lambda name: calls.append(name))

        orig = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = fake
        try:
            prefetch_tiktoken_encodings(AppConfig(tiktoken_prefetch=True))
        finally:
            if orig is None:
                sys.modules.pop("tiktoken", None)
            else:
                sys.modules["tiktoken"] = orig

        self.assertEqual(calls, ["cl100k_base"])

    def test_prefetch_custom_encodings(self):
        from config import AppConfig, prefetch_tiktoken_encodings

        calls = []
        fake = types.SimpleNamespace(get_encoding=lambda name: calls.append(name))

        orig = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = fake
        try:
            prefetch_tiktoken_encodings(
                AppConfig(
                    tiktoken_prefetch=True,
                    tiktoken_prefetch_encodings=["cl100k_base", "o200k_base"],
                )
            )
        finally:
            if orig is None:
                sys.modules.pop("tiktoken", None)
            else:
                sys.modules["tiktoken"] = orig

        self.assertEqual(calls, ["cl100k_base", "o200k_base"])
