"""Backward-compatible import path.

The preferred entrypoint is now the root-level `indexer.py`.
This module remains to avoid breaking existing imports like:
`python -m api.indexer` and tests that import `scan_java_methods`.
"""

from indexer import (  # noqa: F401
    index_codebase,
    iter_java_files,
    main,
    scan_java_methods,
)


if __name__ == "__main__":
    main()
