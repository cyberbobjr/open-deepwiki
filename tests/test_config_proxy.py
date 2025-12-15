import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigProxyEnv(unittest.TestCase):
    def setUp(self) -> None:
        # Snapshot env we touch.
        self._keys = [
            "http_proxy",
            "HTTP_PROXY",
            "https_proxy",
            "HTTPS_PROXY",
            "no_proxy",
            "NO_PROXY",
            "TIKTOKEN_CACHE_DIR",
        ]
        self._orig = {k: os.environ.get(k) for k in self._keys}

        # Clear keys for clean tests.
        for k in self._keys:
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        for k in self._keys:
            os.environ.pop(k, None)
        for k, v in self._orig.items():
            if v is not None:
                os.environ[k] = v

    def test_apply_config_sets_proxy_and_tiktoken_env(self):
        from config import AppConfig, apply_config_to_env

        cfg = AppConfig(
            http_proxy="http://proxy.local:3128",
            https_proxy="http://proxy.local:3128",
            no_proxy="127.0.0.1,localhost",
            tiktoken_cache_dir="/tmp/tiktoken-cache",
        )
        apply_config_to_env(cfg)

        self.assertEqual(os.environ.get("http_proxy"), "http://proxy.local:3128")
        self.assertEqual(os.environ.get("HTTP_PROXY"), "http://proxy.local:3128")
        self.assertEqual(os.environ.get("https_proxy"), "http://proxy.local:3128")
        self.assertEqual(os.environ.get("HTTPS_PROXY"), "http://proxy.local:3128")
        self.assertEqual(os.environ.get("no_proxy"), "127.0.0.1,localhost")
        self.assertEqual(os.environ.get("NO_PROXY"), "127.0.0.1,localhost")
        self.assertEqual(os.environ.get("TIKTOKEN_CACHE_DIR"), "/tmp/tiktoken-cache")

    def test_apply_config_does_not_override_existing_env(self):
        from config import AppConfig, apply_config_to_env

        os.environ["HTTP_PROXY"] = "http://already-set:8080"
        os.environ["TIKTOKEN_CACHE_DIR"] = "/already"

        cfg = AppConfig(
            http_proxy="http://proxy.local:3128",
            tiktoken_cache_dir="/tmp/tiktoken-cache",
        )
        apply_config_to_env(cfg)

        self.assertEqual(os.environ.get("HTTP_PROXY"), "http://already-set:8080")
        self.assertEqual(os.environ.get("TIKTOKEN_CACHE_DIR"), "/already")
        # Lower-case still gets set if missing.
        self.assertEqual(os.environ.get("http_proxy"), "http://proxy.local:3128")
