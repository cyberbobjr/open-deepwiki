from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


def _safe_resolve_path(*, root_dir: Path, user_path: str) -> Path:
    root = root_dir.expanduser().resolve()
    raw = Path(user_path).expanduser()

    candidate = raw if raw.is_absolute() else (root / raw)
    resolved = candidate.resolve()

    if resolved != root and root not in resolved.parents:
        raise ValueError(
            f"Path '{user_path}' resolves outside sandbox root '{root}'."
        )

    return resolved


def make_codebase_tools(*, root_dir: str):
    """Create filesystem tools for a LangChain agent.

    Tools are sandboxed to `root_dir` to avoid path traversal.
    """

    sandbox_root = Path(root_dir)

    @tool("browse_dir")
    def browse_dir(path: str = ".", max_entries: int = 200) -> str:
        """List the contents of a directory (non-recursive).

        Args:
            path: Directory path (absolute or relative to the sandbox root).
            max_entries: Maximum number of entries to return.

        Returns:
            Newline-separated entries. Directories end with '/'.
        """

        try:
            target = _safe_resolve_path(root_dir=sandbox_root, user_path=path)
        except Exception as e:
            return f"ERROR: {e}"

        if not target.exists():
            return f"ERROR: Path does not exist: {target}"
        if not target.is_dir():
            return f"ERROR: Not a directory: {target}"

        try:
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception as e:
            return f"ERROR: Failed to list directory: {e}"

        lines = []
        for p in entries[: max(0, int(max_entries))]:
            name = p.name + ("/" if p.is_dir() else "")
            lines.append(name)

        if len(entries) > max_entries:
            lines.append(f"… ({len(entries) - max_entries} more)")

        return "\n".join(lines) if lines else "(empty)"

    @tool("get_file_contents")
    def get_file_contents(
        path: str,
        start_line: int = 1,
        end_line: int = 200,
        max_chars: int = 20000,
    ) -> str:
        """Read a slice of a text file.

        Args:
            path: File path (absolute or relative to the sandbox root).
            start_line: 1-based inclusive.
            end_line: 1-based inclusive.
            max_chars: Output character limit for safety.

        Returns:
            File excerpt with line numbers.
        """

        try:
            target = _safe_resolve_path(root_dir=sandbox_root, user_path=path)
        except Exception as e:
            return f"ERROR: {e}"

        if not target.exists():
            return f"ERROR: File does not exist: {target}"
        if not target.is_file():
            return f"ERROR: Not a file: {target}"

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"ERROR: Failed to read file: {e}"

        s = max(1, int(start_line))
        e = max(s, int(end_line))
        # Hard cap to avoid runaway prompts.
        if e - s > 600:
            e = s + 600

        lines = text.splitlines()
        if not lines:
            return "(empty file)"

        if s > len(lines):
            return f"ERROR: start_line={s} beyond EOF (lines={len(lines)})"

        excerpt = []
        for idx in range(s, min(e, len(lines)) + 1):
            excerpt.append(f"{idx:5d}: {lines[idx - 1]}")

        out = "\n".join(excerpt)
        if len(out) > int(max_chars):
            out = out[: int(max_chars)] + "\n… (truncated)"

        return out

    return [browse_dir, get_file_contents]
