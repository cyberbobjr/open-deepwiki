from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from core.parsing.java_parser import JavaParser
from core.parsing.tree_sitter_setup import setup_java_language
from core.documentation.postimplementation_log import PostImplementationLog
from indexer import iter_java_files
from utils.chat import create_chat_model


@dataclass(frozen=True)
class JavadocEdit:
    start: int
    end: int
    file_path: Path
    signature: str
    member_type: str
    javadoc_block: str
    reason: str


_JAVADOC_SYSTEM_PROMPT = (
    "You write JavaDoc for Java code. "
    "Return ONLY a valid JavaDoc block comment that starts with '/**' and ends with '*/'. "
    "No markdown, no extra text. "
    "Write thorough, non-concise JavaDoc that fully describes behavior and intent. "
    "For classes/interfaces/enums: describe responsibility, key concepts/invariants, and usage notes when evident. "
    "For methods/constructors: describe what it does, important edge cases, side effects, and any assumptions visible in the code. "
    "Include @param tags for each parameter when parameters exist; include @return when non-void. "
    "Include @throws only when obvious from the code."
)


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _indent_block(block: str, indent: str) -> str:
    lines = _normalize_line_endings(block).split("\n")
    return "\n".join((indent + line if line else indent.rstrip(" \t")) for line in lines)


def _line_start_offset(code: str, offset: int) -> int:
    idx = code.rfind("\n", 0, offset)
    return 0 if idx == -1 else idx + 1


def _leading_indent(code: str, line_start: int, offset: int) -> str:
    segment = code[line_start:offset]
    m = re.match(r"[\t ]*", segment)
    return m.group(0) if m else ""


def _extract_member_nodes(parser: JavaParser, java_code: str) -> Sequence[Tuple[Any, str]]:
    tree = parser.parser.parse(bytes(java_code, "utf8"))
    query = parser.java_language.query(
        """
        (class_declaration) @class
        (interface_declaration) @interface
        (enum_declaration) @enum
        (method_declaration) @method
        (constructor_declaration) @constructor
        """
    )
    return query.captures(tree.root_node)


def _javadoc_meaningful_line_count(javadoc: str) -> int:
    lines = _normalize_line_endings(javadoc).split("\n")
    meaningful = 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s in {"/**", "*/"}:
            continue
        if s == "*":
            continue
        if s.startswith("* "):
            s = s[2:].strip()
        elif s.startswith("*"):
            s = s[1:].strip()
        if not s:
            continue
        meaningful += 1
    return meaningful


def _should_regenerate_existing_javadoc(javadoc: str, *, min_meaningful_lines: int) -> bool:
    # Only "improve" very short docs; longer existing docs are left intact.
    return _javadoc_meaningful_line_count(javadoc) < int(min_meaningful_lines)


def _find_existing_javadoc_region(parser: JavaParser, node: Any, code: str) -> Optional[Tuple[int, int, str]]:
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
            if comment_text.strip().startswith("/**"):
                start = _line_start_offset(code, prev_sibling.start_byte)
                end = _line_start_offset(code, node.start_byte)
                return (start, end, comment_text)

    lookback_start = max(0, node.start_byte - 4000)
    prefix = code[lookback_start : node.start_byte]
    match = re.search(r"(/\*\*[\s\S]*?\*/)[\s]*\Z", prefix)
    if match:
        comment_text = match.group(1)
        comment_start = lookback_start + match.start(1)
        start = _line_start_offset(code, comment_start)
        end = _line_start_offset(code, node.start_byte)
        return (start, end, comment_text)

    return None


def _extract_type_signature(node: Any, code: str, kind: str) -> str:
    signature_parts: List[str] = []

    for child in getattr(node, "children", []) or []:
        if child.type in ["modifiers", "identifier", "type_parameters"]:
            signature_parts.append(code[child.start_byte : child.end_byte])

    base = " ".join(signature_parts).strip()
    return f"{kind} {base}".strip()


def _ensure_javadoc_only(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("/**"):
        # Try to recover if model included leading text.
        start = stripped.find("/**")
        if start != -1:
            stripped = stripped[start:]
    if not stripped.endswith("*/"):
        end = stripped.rfind("*/")
        if end != -1:
            stripped = stripped[: end + 2]
    return stripped.strip()


def generate_missing_javadoc_in_directory(
    root_dir: str,
    *,
    log_dir: str,
    llm: Optional[Any] = None,
    max_code_chars: int = 4000,
    stop_event: Optional[threading.Event] = None,
    min_meaningful_lines: int = 3,
) -> Dict[str, Any]:
    """Recursively scans a Java project and generates missing JavaDoc.

    - Uses tree-sitter to locate methods/constructors.
    - For members without JavaDoc, asks the chat model for a JavaDoc block.
    - Applies edits to files and writes a postimplementation log.

    Returns a summary dict suitable for API responses.
    """

    setup_java_language()
    parser = JavaParser()

    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    model = llm or create_chat_model(temperature=0.0)

    log = PostImplementationLog.create(log_dir)
    log.write_header(str(root))

    files = list(iter_java_files(str(root)))

    files_modified = 0
    members_documented = 0

    for file_path in files:
        if stop_event is not None and stop_event.is_set():
            break

        original = file_path.read_text(encoding="utf-8")
        code = _normalize_line_endings(original)

        edits: List[JavadocEdit] = []

        captures = _extract_member_nodes(parser, code)
        for node, capture_name in captures:
            if stop_event is not None and stop_event.is_set():
                break

            existing_region = _find_existing_javadoc_region(parser, node, code)
            existing_text = existing_region[2] if existing_region else None
            if existing_text and existing_text.strip().startswith("/**"):
                if not _should_regenerate_existing_javadoc(
                    existing_text,
                    min_meaningful_lines=min_meaningful_lines,
                ):
                    continue

            if capture_name in {"class", "interface", "enum"}:
                signature = _extract_type_signature(node, code, capture_name)
                member_type = capture_name
            else:
                signature = parser._extract_signature(node, code)
                member_type = "method" if capture_name == "method" else "constructor"

            snippet = code[node.start_byte : node.end_byte]
            if len(snippet) > max_code_chars:
                snippet = snippet[:max_code_chars] + "\n// ... truncated ...\n"

            user_prompt = "\n\n".join(
                [
                    f"Signature: {signature}",
                    f"Type: {member_type}",
                    "Code:",
                    snippet,
                ]
            )

            if stop_event is not None and stop_event.is_set():
                break

            response = model.invoke(
                [
                    SystemMessage(content=_JAVADOC_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )
            content = getattr(response, "content", None)
            if not isinstance(content, str):
                content = str(response)

            javadoc = _ensure_javadoc_only(content)
            if not javadoc.startswith("/**") or not javadoc.endswith("*/"):
                # Skip if the model didn't comply.
                continue

            line_start = _line_start_offset(code, node.start_byte)
            indent = _leading_indent(code, line_start, node.start_byte)
            indented = _indent_block(javadoc, indent)
            insertion = indented + "\n"

            if existing_region is not None:
                edit_start, edit_end, _ = existing_region
                reason = "short_javadoc"
            else:
                edit_start = line_start
                edit_end = line_start
                reason = "missing_javadoc"

            edits.append(
                JavadocEdit(
                    start=edit_start,
                    end=edit_end,
                    file_path=file_path,
                    signature=signature,
                    member_type=member_type,
                    javadoc_block=insertion,
                    reason=reason,
                )
            )

        if not edits:
            continue

        # Apply from bottom to top to keep offsets stable.
        edits_sorted = sorted(edits, key=lambda e: e.start, reverse=True)
        updated = code
        for edit in edits_sorted:
            updated = updated[: edit.start] + edit.javadoc_block + updated[edit.end :]
            log.append_change(
                file_path=str(edit.file_path),
                signature=edit.signature,
                member_type=edit.member_type,
                reason=edit.reason,
            )
            members_documented += 1

        if updated != code:
            # Preserve original line endings choice if it used CRLF.
            if "\r\n" in original:
                updated_to_write = updated.replace("\n", "\r\n")
            else:
                updated_to_write = updated

            file_path.write_text(updated_to_write, encoding="utf-8")
            files_modified += 1

    return {
        "root_dir": str(root),
        "files_scanned": len(files),
        "files_modified": files_modified,
        "members_documented": members_documented,
        "log_file": str(log.path),
    }
