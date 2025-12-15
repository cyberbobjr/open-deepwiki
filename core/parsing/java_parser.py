from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class JavaMethod:
    """Represents a parsed Java method or constructor."""

    id: str
    signature: str
    type: str  # "method" or "constructor"
    calls: List[str]
    code: str
    javadoc: Optional[str] = None


class JavaParser:
    """Parser for Java code using tree-sitter."""

    def __init__(self):
        lib_path = "build/java-languages.so"
        if not os.path.exists(lib_path):
            raise RuntimeError(
                "Tree-sitter Java language library not found at 'build/java-languages.so'. "
                "Run setup_java_language() to build it first."
            )

        # Delay tree-sitter imports so other modules can be imported without it.
        import tree_sitter  # type: ignore
        from tree_sitter import Language, Parser  # type: ignore

        self._tree_sitter = tree_sitter
        self.java_language = Language(lib_path, "java")
        self.parser = Parser()
        self.parser.set_language(self.java_language)

    def parse_java_file(self, java_code: str) -> List[JavaMethod]:
        tree = self.parser.parse(bytes(java_code, "utf8"))
        methods: List[JavaMethod] = []

        query = self.java_language.query(
            """
            (method_declaration) @method
            (constructor_declaration) @constructor
        """
        )

        captures = query.captures(tree.root_node)

        for node, capture_name in captures:
            method_type = "method" if capture_name == "method" else "constructor"
            signature = self._extract_signature(node, java_code)
            method_id = self._generate_id(signature)
            code = java_code[node.start_byte : node.end_byte]
            calls = self._extract_calls(node, java_code)
            javadoc = self._extract_javadoc(node, java_code)

            methods.append(
                JavaMethod(
                    id=method_id,
                    signature=signature,
                    type=method_type,
                    calls=calls,
                    code=code,
                    javadoc=javadoc,
                )
            )

        return methods

    def _extract_signature(self, node, code: str) -> str:
        signature_parts: List[str] = []

        for child in node.children:
            if child.type in ["modifiers", "type_identifier", "void_type", "generic_type"]:
                signature_parts.append(code[child.start_byte : child.end_byte])
            elif child.type == "identifier":
                signature_parts.append(code[child.start_byte : child.end_byte])
            elif child.type == "formal_parameters":
                signature_parts.append(code[child.start_byte : child.end_byte])

        return " ".join(signature_parts).strip()

    def _generate_id(self, signature: str) -> str:
        cleaned = re.sub(r"\s+", "_", signature)
        cleaned = re.sub(r"[^\w_]", "", cleaned)
        return cleaned.lower()

    def _extract_calls(self, node, code: str) -> List[str]:
        calls: List[str] = []

        query = self.java_language.query(
            """
            (method_invocation
                name: (identifier) @call_name)
        """
        )

        captures = query.captures(node)

        for call_node, _ in captures:
            call_name = code[call_node.start_byte : call_node.end_byte]
            calls.append(call_name)

        return list(set(calls))

    def _extract_javadoc(self, node, code: str) -> Optional[str]:
        parent = node.parent
        if not parent:
            return None

        node_index = None
        for i, child in enumerate(parent.children):
            if (
                child.type == node.type
                and child.start_byte == node.start_byte
                and child.end_byte == node.end_byte
            ):
                node_index = i
                break

        if node_index is not None and node_index > 0:
            prev_sibling = parent.children[node_index - 1]
            if prev_sibling.type == "block_comment":
                comment_text = code[prev_sibling.start_byte : prev_sibling.end_byte]
                if comment_text.startswith("/**"):
                    return comment_text

        lookback_start = max(0, node.start_byte - 4000)
        prefix = code[lookback_start : node.start_byte]
        match = re.search(r"(/\*\*[\s\S]*?\*/)[\s]*\Z", prefix)
        if match:
            return match.group(1)

        return None
