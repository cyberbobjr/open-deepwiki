from __future__ import annotations

import os
import re
from typing import List, Optional

from core.parsing.base import BaseParser
from core.parsing.models import CodeBlock


class PythonParser(BaseParser):
    """Parser for Python code using tree-sitter."""

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
        self.language = Language(lib_path, "python")
        self.parser = Parser()
        self.parser.set_language(self.language)

    def parse_file(self, code: str, *, file_path: Optional[str] = None) -> List[CodeBlock]:
        tree = self.parser.parse(bytes(code, "utf8"))
        blocks: List[CodeBlock] = []

        query = self.language.query(
            """
            (function_definition) @function
            (class_definition) @class
            """
        )

        captures = query.captures(tree.root_node)
        code_bytes = bytes(code, "utf8")

        for node, capture_name in captures:
            type_label = "function" if capture_name == "function" else "class"
            
            signature = self._extract_signature(node, code_bytes)
            block_content = code_bytes[node.start_byte : node.end_byte].decode("utf8")
            calls = self._extract_calls(node, code_bytes)
            docstring = self._extract_docstring(node, code_bytes)

            start_line = int(getattr(node, "start_point", (0, 0))[0]) + 1
            end_line = int(getattr(node, "end_point", (0, 0))[0]) + 1

            # Generate ID
            # Python structure is flatter but can have nested functions/classes.
            # We can use file path + name + line for uniqueness.
            
            # TODO: Improve enclosure extraction for python (nested functions)
            
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
                    language="python",
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
        # For python, signature is usually the name + parameters.
        # (function_definition name: (identifier) parameters: (parameters))
        
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        
        name = ""
        if name_node:
            name = code[name_node.start_byte : name_node.end_byte].decode("utf8")
        
        params = "()"
        if params_node:
            params = code[params_node.start_byte : params_node.end_byte].decode("utf8")
            
        return f"def {name}{params}"

    def _extract_calls(self, node, code: bytes) -> List[str]:
        # (call function: (identifier))
        query = self.language.query(
            """
            (call function: (identifier) @call_name)
            (call function: (attribute attribute: (identifier) @call_name))
            """
        )
        calls = []
        for call_node, _ in query.captures(node):
            name = code[call_node.start_byte : call_node.end_byte].decode("utf8")
            calls.append(name)
        return list(set(calls))

    def _extract_docstring(self, node, code: bytes) -> Optional[str]:
        # Docstring is the first expression statement in the body that is a string
        body_node = node.child_by_field_name("body")
        if not body_node:
            return None
            
        for child in body_node.children:
            if child.type == "expression_statement":
                # Check if it contains a string
                if child.children and child.children[0].type == "string":
                    string_node = child.children[0]
                    text = code[string_node.start_byte : string_node.end_byte].decode("utf8")
                    # Remove quotes
                    return text.strip().strip('"""').strip("'''").strip('"').strip("'")
            elif child.type == "comment":
                continue
            else:
                # If we hit logic before a docstring, then no docstring
                break
        return None

    def _generate_id(self, signature: str, file_path: Optional[str], start_line: int) -> str:
        # Simple ID generation
        parts = []
        if file_path:
            parts.append(file_path)
            
        parts.append(signature)
        parts.append(f"l{start_line}")
        
        raw = "::".join(parts)
        # Clean special chars
        return re.sub(r"[^\w\-\.:]", "_", raw).lower()
