from __future__ import annotations

import os
import re
from typing import List, Optional

from core.parsing.base import BaseParser
from core.parsing.models import CodeBlock


class TypeScriptParser(BaseParser):
    """Parser for TypeScript code using tree-sitter."""

    def __init__(self):
        lib_path = "build/languages.so"
        if not os.path.exists(lib_path):
            raise RuntimeError(
                "Tree-sitter languages library not found at 'build/languages.so'. "
                "Run setup_languages() to build it first."
            )

        import tree_sitter  # type: ignore
        from tree_sitter import Language, Parser  # type: ignore

        self._tree_sitter = tree_sitter
        self.language = Language(lib_path, "typescript")
        self.parser = Parser()
        self.parser.set_language(self.language)

    def parse_file(self, code: str, *, file_path: Optional[str] = None) -> List[CodeBlock]:
        tree = self.parser.parse(bytes(code, "utf8"))
        blocks: List[CodeBlock] = []

        query = self.language.query(
            """
            (function_declaration) @function
            (method_definition) @method
            (class_declaration) @class
            (interface_declaration) @interface
            (arrow_function) @arrow_func  
            """
        ) # Arrow functions might be too granular, but good to have.

        captures = query.captures(tree.root_node)
        code_bytes = bytes(code, "utf8")

        for node, capture_name in captures:
            # Map capture to type
            type_map = {
                "function": "function",
                "method": "method",
                "class": "class",
                "interface": "interface",
                "arrow_func": "arrow_function"
            }
            type_label = type_map.get(capture_name, "block")
            
            signature = self._extract_signature(node, code_bytes)
            block_content = code_bytes[node.start_byte : node.end_byte].decode("utf8")
            calls = self._extract_calls(node, code_bytes)
            # JSDoc extraction is tricky in TS (often comment preceding node)
            docstring = self._extract_jsdoc(node, code_bytes)

            start_line = int(getattr(node, "start_point", (0, 0))[0]) + 1
            end_line = int(getattr(node, "end_point", (0, 0))[0]) + 1

            block_id = self._generate_id(
                signature,
                file_path=file_path,
                start_line=start_line
            )

            blocks.append(
                CodeBlock(
                    id=block_id,
                    signature=signature,
                    type=type_label,
                    language="typescript",
                    calls=calls,
                    code=block_content,
                    docstring=docstring,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                )
            )

        return blocks

    def _extract_signature(self, node, code: bytes) -> str:
        # Rough signature extraction: name + params or just first line
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        
        name = "anonymous"
        if name_node:
            name = code[name_node.start_byte : name_node.end_byte].decode("utf8")
            
        params = ""
        if params_node:
            params = code[params_node.start_byte : params_node.end_byte].decode("utf8")
        
        return f"{name}{params}"

    def _extract_calls(self, node, code: bytes) -> List[str]:
        query = self.language.query(
            """
            (call_expression
                function: (identifier) @call)
            (call_expression
                function: (member_expression property: (property_identifier) @call))
            """
        )
        calls = []
        for call_node, _ in query.captures(node):
            name = code[call_node.start_byte : call_node.end_byte].decode("utf8")
            calls.append(name)
        return list(set(calls))

    def _extract_jsdoc(self, node, code: bytes) -> Optional[str]:
        # Inspect previous sibling for comment
        # Note: tree-sitter sometimes wraps comments in the node, but usually siblings for JS/TS
        
        # Access parent's children to find self index
        parent = node.parent
        if not parent:
            return None
            
        children = parent.children
        # Find explicit index (could be optimized)
        for i, child in enumerate(children):
            if child.id == node.id:
                if i > 0:
                    prev = children[i-1]
                    if prev.type == "comment":
                        text = code[prev.start_byte : prev.end_byte].decode("utf8")
                        if text.startswith("/**"):
                            return text
                break
        return None

    def _generate_id(self, signature: str, file_path: Optional[str], start_line: int) -> str:
        parts = []
        if file_path:
            parts.append(file_path)
        parts.append(signature)
        parts.append(f"l{start_line}")
        return re.sub(r"[^\w\-\.:]", "_", "::".join(parts)).lower()
