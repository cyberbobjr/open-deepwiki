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
    # Optional context filled by higher-level scanners (e.g. indexer scanning a directory)
    file_path: Optional[str] = None
    project: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None


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

    def parse_java_file(self, java_code: str, *, file_path: Optional[str] = None) -> List[JavaMethod]:
        """Parse a single Java source file and extract methods/constructors.

        Args:
            java_code: Full Java source text.
            file_path: Optional path of the source file being parsed.
                Used only to help generate stable, unique method IDs across a codebase.

        Returns:
            A list of parsed Java methods/constructors.
        """

        tree = self.parser.parse(bytes(java_code, "utf8"))
        methods: List[JavaMethod] = []

        query = self.java_language.query(
            """
            (method_declaration) @method
            (constructor_declaration) @constructor
        """
        )

        captures = query.captures(tree.root_node)

        # Convert to bytes once for all subsequent operations
        code_bytes = bytes(java_code, "utf8")
        package_name = self._extract_package_name(tree.root_node, code_bytes)

        for node, capture_name in captures:
            method_type = "method" if capture_name == "method" else "constructor"
            
            signature = self._extract_signature(node, code_bytes)
            code = code_bytes[node.start_byte : node.end_byte].decode("utf8")
            calls = self._extract_calls(node, code_bytes)
            javadoc = self._extract_javadoc(node, code_bytes)

            # tree-sitter exposes 0-based (row, column) points.
            start_line = int(getattr(node, "start_point", (0, 0))[0]) + 1
            end_line = int(getattr(node, "end_point", (0, 0))[0]) + 1

            enclosing_type = self._extract_enclosing_type_name(node, code_bytes)
            method_id = self._generate_id(
                signature,
                package_name=package_name,
                enclosing_type=enclosing_type,
                start_line=start_line,
                file_path=file_path,
            )

            methods.append(
                JavaMethod(
                    id=method_id,
                    signature=signature,
                    type=method_type,
                    calls=calls,
                    code=code,
                    javadoc=javadoc,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                )
            )

        return methods

    def _extract_signature(self, node, code: bytes) -> str:
        signature_parts: List[str] = []

        for child in node.children:
            if child.type in ["modifiers", "type_identifier", "void_type", "generic_type"]:
                signature_parts.append(code[child.start_byte : child.end_byte].decode("utf8"))
            elif child.type == "identifier":
                signature_parts.append(code[child.start_byte : child.end_byte].decode("utf8"))
            elif child.type == "formal_parameters":
                signature_parts.append(code[child.start_byte : child.end_byte].decode("utf8"))

        return " ".join(signature_parts).strip()

    def _generate_id(
        self,
        signature: str,
        *,
        package_name: Optional[str] = None,
        enclosing_type: Optional[str] = None,
        start_line: Optional[int] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """Generate a stable, codebase-unique identifier for a method.

        Notes:
            The previous implementation derived IDs only from the extracted signature,
            which can collide across different classes/files (common in real codebases).
            We include extra context to reduce collisions, while keeping IDs readable.

        Args:
            signature: Extracted method/constructor signature string.
            package_name: Optional package name (e.g., "com.example").
            enclosing_type: Optional enclosing type name (class/interface/enum/record).
            start_line: Optional 1-based start line of the declaration.
            file_path: Optional file path used as last-resort uniqueness salt.

        Returns:
            A lowercase, filesystem-safe identifier.
        """

        parts: List[str] = []
        if package_name:
            parts.append(package_name)
        if enclosing_type:
            parts.append(enclosing_type)

        parts.append(signature)

        # Line number makes collisions extremely unlikely even when signature extraction
        # is imperfect or when the same signature appears in multiple files.
        if start_line is not None:
            parts.append(f"l{int(start_line)}")

        # Include file path as a last-resort salt; it should already be stable within a repo.
        if file_path:
            parts.append(str(file_path))

        raw = "::".join([p for p in parts if p])
        cleaned = re.sub(r"\s+", "_", raw)
        cleaned = re.sub(r"[^\w_:\-./]", "", cleaned)
        cleaned = cleaned.replace("/", "_")
        cleaned = cleaned.replace(".", "_")
        cleaned = cleaned.replace(":", "_")
        cleaned = cleaned.replace("-", "_")
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned.lower()

    def _extract_package_name(self, root_node, code: bytes) -> Optional[str]:
        """Extract the package name for a compilation unit, if present.

        Args:
            root_node: Tree-sitter root node.
            code: Full Java source bytes.

        Returns:
            Package name like "com.example" or None if absent.
        """

        try:
            query = self.java_language.query(
                """
                (package_declaration
                    (scoped_identifier) @pkg)
                """
            )
            captures = query.captures(root_node)
            for node, _ in captures:
                name = code[node.start_byte : node.end_byte].decode("utf8").strip()
                if name:
                    return name
        except Exception:
            return None
        return None

    def _extract_enclosing_type_name(self, node, code: bytes) -> Optional[str]:
        """Find the closest enclosing type name (class/interface/enum/record).

        Args:
            node: Tree-sitter node for a method/constructor declaration.
            code: Full Java source bytes.

        Returns:
            Enclosing type name (e.g., "MyService") or None.
        """

        current = getattr(node, "parent", None)
        while current is not None:
            if current.type in {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration",
            }:
                # Most declarations include the simple name as an `identifier` child.
                for child in getattr(current, "children", []) or []:
                    if child.type == "identifier":
                        name = code[child.start_byte : child.end_byte].decode("utf8").strip()
                        return name or None
            current = getattr(current, "parent", None)
        return None

    def _extract_calls(self, node, code: bytes) -> List[str]:
        calls: List[str] = []

        query = self.java_language.query(
            """
            (method_invocation
                name: (identifier) @call_name)
        """
        )

        captures = query.captures(node)

        for call_node, _ in captures:
            call_name = code[call_node.start_byte : call_node.end_byte].decode("utf8")
            calls.append(call_name)

        return list(set(calls))

    def _extract_javadoc(self, node, code: bytes) -> Optional[str]:
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
                comment_text = code[prev_sibling.start_byte : prev_sibling.end_byte].decode("utf8")
                if comment_text.startswith("/**"):
                    return comment_text

        lookback_start = max(0, node.start_byte - 4000)
        prefix = code[lookback_start : node.start_byte].decode("utf8", errors="ignore")
        match = re.search(r"(/\*\*[\s\S]*?\*/)[\s]*\Z", prefix)
        if match:
            return match.group(1)

        return None
