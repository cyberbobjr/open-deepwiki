from __future__ import annotations

import os
import subprocess


def setup_java_language() -> None:
    """Download and build tree-sitter-java if not already available.

    Produces: build/java-languages.so
    """

    # Delay tree-sitter imports so the rest of the app can run without it.
    from tree_sitter import Language  # type: ignore

    os.makedirs("vendor", exist_ok=True)
    os.makedirs("build", exist_ok=True)

    if not os.path.exists("vendor/tree-sitter-java"):
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/tree-sitter/tree-sitter-java",
                "vendor/tree-sitter-java",
            ],
            check=True,
            shell=False,
            timeout=60,
        )

    if not os.path.exists("build/java-languages.so"):
        Language.build_library("build/java-languages.so", ["vendor/tree-sitter-java"])
