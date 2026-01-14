from __future__ import annotations

import os
import subprocess


def setup_languages() -> None:
    """Download and build tree-sitter grammars for supported languages.

    Produces: build/languages.so containing java, python, typescript.
    """

    # Delay tree-sitter imports so the rest of the app can run without it.
    from tree_sitter import Language  # type: ignore

    os.makedirs("vendor", exist_ok=True)
    os.makedirs("build", exist_ok=True)

    repos = {
        "java": "https://github.com/tree-sitter/tree-sitter-java",
        "python": "https://github.com/tree-sitter/tree-sitter-python",
        "typescript": "https://github.com/tree-sitter/tree-sitter-typescript",
    }

    for lang, url in repos.items():
        if not os.path.exists(f"vendor/tree-sitter-{lang}"):
            subprocess.run(
                ["git", "clone", url, f"vendor/tree-sitter-{lang}"],
                check=True,
                shell=False,
                timeout=60,
            )

    output_lib = "build/languages.so"
    
    # Paths to include in the build
    sources = [
        "vendor/tree-sitter-java",
        "vendor/tree-sitter-python",
        "vendor/tree-sitter-typescript/typescript", # Standard TS
        "vendor/tree-sitter-typescript/tsx",        # TSX support
    ]

    # Rebuild if missing or if we might have added new languages (simple check: if file exists)
    # Ideally should check if sources are newer, but for now just check existence.
    if not os.path.exists(output_lib):
        Language.build_library(output_lib, sources)

# Alias for backward compatibility if needed, but we should update callers
setup_java_language = setup_languages
