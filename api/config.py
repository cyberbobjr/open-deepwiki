"""Backward-compatible import path.

The preferred entrypoint is now the root-level `config.py`.
This module remains to avoid breaking existing imports.
"""

from config import AppConfig, DEFAULT_CONFIG_PATH, configure_logging, load_config  # noqa: F401
