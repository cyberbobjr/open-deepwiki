from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from langchain_core.messages import HumanMessage, SystemMessage


@dataclass(frozen=True)
class LLMCallResult:
    """A small wrapper for normalized LLM responses.

    Attributes:
        content: The generated text content.
    """

    content: str


def _coerce_llm_content(response: Any) -> str:
    """Extract text from common LangChain response shapes.

    Args:
        response: LLM response object.

    Returns:
        Best-effort extracted text content.
    """

    if response is None:
        return ""

    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content

    if isinstance(response, dict):
        val = response.get("content") or response.get("text") or ""
        return str(val) if val is not None else ""

    return str(response)


def _invoke_llm(llm: Any, messages: Sequence[Any]) -> LLMCallResult:
    """Invoke a LangChain-compatible chat model.

    Args:
        llm: A LangChain chat model (e.g., ChatOpenAI).
        messages: A list/sequence of System/Human messages.

    Returns:
        Normalized result with `.content`.

    Raises:
        Exception: Propagates model invocation errors.
    """

    if hasattr(llm, "invoke"):
        response = llm.invoke(list(messages))
        return LLMCallResult(content=_coerce_llm_content(response).strip())

    response = llm(list(messages))
    return LLMCallResult(content=_coerce_llm_content(response).strip())


def _truncate_middle(text: str, *, max_chars: int) -> str:
    """Truncate text by keeping the beginning and end.

    Args:
        text: Input text.
        max_chars: Maximum number of characters to return. Must be > 0.

    Returns:
        A possibly-truncated string no longer than `max_chars`.

    Raises:
        ValueError: If `max_chars` is not positive.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if len(text) <= max_chars:
        return text

    prefix_len = int(max_chars * 0.7)
    suffix_len = max_chars - prefix_len

    prefix = text[:prefix_len].rstrip()
    suffix = text[-suffix_len:].lstrip()
    return prefix + "\n\n/* --- TRUNCATED FOR TOKEN LIMITS --- */\n\n" + suffix


def _extract_json_array(text: str) -> List[str]:
    """Parse a JSON array of strings from raw model output.

    Args:
        text: Raw model output.

    Returns:
        Parsed list of strings.

    Raises:
        ValueError: If no JSON list could be parsed.
    """

    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty LLM output; expected JSON list")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return [x.strip() for x in parsed if x.strip()]
    except Exception:
        pass

    match = re.search(r"\[[\s\S]*\]", raw)
    if not match:
        raise ValueError("Could not find a JSON list in model output")

    try:
        parsed = json.loads(match.group(0))
    except Exception as e:
        raise ValueError(f"Failed to parse JSON list: {e}") from e

    if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
        raise ValueError("Parsed JSON was not a list of strings")

    return [x.strip() for x in parsed if x.strip()]


def _extract_json_object(text: str) -> Dict[str, str]:
    """Parse a JSON object mapping strings to strings from model output.

    Args:
        text: Raw model output.

    Returns:
        Dict mapping key -> value.

    Raises:
        ValueError: If parsing fails.
    """

    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty LLM output; expected JSON object")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and all(isinstance(k, str) for k in parsed.keys()):
            out: Dict[str, str] = {}
            for k, v in parsed.items():
                if isinstance(v, str):
                    out[k] = v
                else:
                    out[k] = str(v)
            return out
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("Could not find a JSON object in model output")

    try:
        parsed = json.loads(match.group(0))
    except Exception as e:
        raise ValueError(f"Failed to parse JSON object: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON was not an object")

    out2: Dict[str, str] = {}
    for k, v in parsed.items():
        if not isinstance(k, str):
            continue
        out2[k] = v if isinstance(v, str) else str(v)
    return out2


def _slugify_feature_name(name: str) -> str:
    """Convert a feature name into a safe filename slug.

    Args:
        name: Feature name.

    Returns:
        Lowercase slug suitable for a markdown filename.
    """

    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "feature"


def _extract_file_titles_from_summaries(summaries: Sequence[str]) -> List[str]:
    """Extract file identifiers from file summary markdown.

    The current file summarizer typically starts each section with a Markdown H2:
    '## <file path>'. This function extracts those names for listing.

    Args:
        summaries: File summary markdown chunks.

    Returns:
        A list of extracted file names/paths.
    """

    results: List[str] = []
    for summary in summaries:
        first_line = (summary or "").lstrip().splitlines()[0] if (summary or "").strip() else ""
        if first_line.startswith("## "):
            results.append(first_line[3:].strip())
    return [x for x in results if x]


class DocumentationSiteGenerator:
    """Generate a feature-based documentation site from an existing project overview.

    The generator pivots from a folder-based overview into a feature-based site:
    - Step A: derive a feature taxonomy from the global project overview
    - Step B: map file summaries into features (semantic classification)
    - Step C: generate one markdown page per feature
    """

    def __init__(
        self,
        llm: Any,
        *,
        batch_size: int = 10,
        max_input_chars: int = 60_000,
    ) -> None:
        """Create a generator.

        Args:
            llm: LangChain chat model to use.
            batch_size: Number of files to classify per LLM call.
            max_input_chars: Maximum characters to send to the model per request.

        Raises:
            ValueError: If `batch_size` is not positive.
        """

        if int(batch_size) <= 0:
            raise ValueError("batch_size must be > 0")
        self._llm = llm
        self._batch_size = int(batch_size)
        self._max_input_chars = int(max_input_chars)

    def generate_feature_list(self, project_overview: str) -> List[str]:
        """Generate a list of top-level features from the project overview.

        Args:
            project_overview: Global overview markdown text.

        Returns:
            A list of 5-10 feature names.

        Raises:
            ValueError: If the model response cannot be parsed.
        """

        overview = _truncate_middle(project_overview or "", max_chars=self._max_input_chars)

        system = SystemMessage(
            content=(
                "You are a senior software analyst. Extract a compact feature taxonomy from a project overview. "
                "Return ONLY JSON."
            )
        )
        human = HumanMessage(
            content=(
                "From the following PROJECT OVERVIEW, extract 5-10 primary functional topics (features).\n\n"
                "Rules:\n"
                "- Output MUST be a JSON array of strings.\n"
                "- Prefer user-facing or business capabilities over folder names.\n"
                "- Keep names short and consistent (Title Case).\n\n"
                "PROJECT OVERVIEW:\n"
                f"{overview}"
            )
        )

        result = _invoke_llm(self._llm, [system, human]).content
        features = _extract_json_array(result)

        # De-duplicate while preserving order.
        seen: set[str] = set()
        uniq: List[str] = []
        for f in features:
            if f not in seen:
                uniq.append(f)
                seen.add(f)

        return uniq

    def map_files_to_features(
        self,
        file_summaries: Mapping[str, str],
        feature_list: Sequence[str],
    ) -> Dict[str, List[str]]:
        """Map files into features by classifying file summaries.

        Args:
            file_summaries: Mapping of file path -> file summary markdown.
            feature_list: Candidate features to assign each file into.

        Returns:
            Mapping of feature name -> list of file paths assigned to it.

        Raises:
            ValueError: If `feature_list` is empty.
        """

        features = [f.strip() for f in (feature_list or []) if (f or "").strip()]
        if not features:
            raise ValueError("feature_list must not be empty")

        files = [(k, v) for k, v in (file_summaries or {}).items() if (k or "").strip()]
        batches: List[List[Tuple[str, str]]] = []
        for i in range(0, len(files), self._batch_size):
            batches.append(files[i : i + self._batch_size])

        assignments: Dict[str, str] = {}

        system = SystemMessage(
            content=(
                "You are a senior software analyst performing zero-shot classification. "
                "Assign each file to exactly ONE feature from the provided list. "
                "Return ONLY JSON."
            )
        )

        for batch in batches:
            payload_items: List[Dict[str, str]] = []
            for path, summary in batch:
                payload_items.append(
                    {
                        "file": path,
                        "summary": _truncate_middle(summary or "", max_chars=6_000),
                    }
                )

            human = HumanMessage(
                content=(
                    "Classify each file into the single most relevant feature.\n\n"
                    "FEATURE LIST:\n"
                    f"{json.dumps(features, ensure_ascii=False)}\n\n"
                    "FILES (JSON array of objects with fields 'file' and 'summary'):\n"
                    f"{json.dumps(payload_items, ensure_ascii=False)}\n\n"
                    "Return a JSON object mapping file -> feature. "
                    "Each value MUST be one of the provided features."
                )
            )

            raw = _invoke_llm(self._llm, [system, human]).content
            parsed = _extract_json_object(raw)

            for file_path, feature in parsed.items():
                assignments[file_path] = (feature or "").strip()

        # Ensure every file got assigned.
        default_feature = features[0]
        for file_path, _summary in files:
            if file_path not in assignments or assignments[file_path] not in features:
                assignments[file_path] = default_feature

        by_feature: Dict[str, List[str]] = {f: [] for f in features}
        for file_path, feature in sorted(assignments.items(), key=lambda kv: kv[0]):
            by_feature.setdefault(feature, []).append(file_path)

        return by_feature

    def generate_feature_page(
        self,
        feature_name: str,
        related_file_summaries: Sequence[str],
    ) -> str:
        """Generate a detailed markdown page for a feature.

        Args:
            feature_name: Feature name.
            related_file_summaries: Summaries of files relevant to this feature.

        Returns:
            Markdown page contents.
        """

        name = (feature_name or "").strip() or "Feature"
        summaries = [s.strip() for s in (related_file_summaries or []) if (s or "").strip()]
        joined = _truncate_middle("\n\n".join(summaries), max_chars=self._max_input_chars)

        system = SystemMessage(
            content=(
                "You are generating DeepWiki-style feature documentation. "
                "Use ONLY the provided file summaries. Return clean Markdown. "
                "Do not include fenced code blocks, EXCEPT when using Mermaid diagrams. "
                "You MUST include at least one Mermaid SEQUENCE diagram and at least one Mermaid CLASS diagram "
                "to explain the logic and structure. Use the exact format: ```mermaid\n...\n``` . "
                "Do not include any other code fences (no ```java, ```python, etc)."
            )
        )

        human = HumanMessage(
            content=(
                "Write a detailed feature page in Markdown.\n\n"
                "Required structure:\n"
                "1) High-Level Concept (what purpose this feature serves)\n"
                "2) Implementation Details (how the files collaborate)\n"
                "3) Key Classes/Methods (mention specific elements from the summaries)\n\n"
                "Diagram Requirements:\n"
                "Include at least ONE Mermaid sequence diagram explaining the main flow.\n"
                "- Include at least ONE Mermaid class diagram explaining the relationships.\n"
                "- Mermaid Syntax Rules:\n"
                "  1) Use exactly ONE statement per line. Never put multiple statements on one line.\n"
                "  2) For `classDiagram`: use `class ClassName` (e.g. `class JavaConfiguration`), id1 --> id2.\n"
                "  3) For `sequenceDiagram`: use `participant A` and `A->>B: message`.\n"
                "  4) Ensure node IDs are alphanumeric only (e.g. id1, id2), no brackets/parentheses.\n"
                "  5) Avoid complex styling, colors, or unbalanced quotes.\n"
                "- Keep it simple (< 30 lines).\n\n"
                f"Feature: {name}\n\n"
                "File summaries:\n"
                f"{joined}"
            )
        )

        body = _invoke_llm(self._llm, [system, human]).content.strip()
        if not body:
            body = "_No content generated._"

        # Add a consistent header and a related-file list extracted locally.
        files = _extract_file_titles_from_summaries(summaries)
        files_section = "\n".join([f"- {f}" for f in files])

        related_files_block = ""
        if files_section:
            related_files_block = f"\n\n## Related Files\n{files_section}\n"

        if body.lstrip().startswith("#"):
            return body + related_files_block + "\n"

        return f"# {name}\n\n{body}\n" + related_files_block + "\n"

    def feature_filename(self, feature_name: str) -> str:
        """Get the canonical filename for a feature page.

        Args:
            feature_name: Feature name.

        Returns:
            Filename like 'authentication.md'.
        """

        return f"{_slugify_feature_name(feature_name)}.md"


def write_feature_docs_site(
    *,
    output_dir: Path,
    project_overview: str,
    file_summaries: Mapping[str, str],
    llm: Any,
    batch_size: int = 10,
) -> Dict[str, Path]:
    """Generate a feature-based docs site on disk.

    Args:
        output_dir: Directory where `index.md` and `features/` will be written.
        project_overview: Global overview markdown.
        file_summaries: Mapping of file path -> file summary markdown.
        llm: LangChain chat model.
        batch_size: Batch size for file-to-feature mapping.

    Returns:
        Mapping of feature name -> path of generated feature page.
    """

    generator = DocumentationSiteGenerator(llm, batch_size=batch_size)
    features = generator.generate_feature_list(project_overview)
    mapping = generator.map_files_to_features(file_summaries, features)

    output_dir.mkdir(parents=True, exist_ok=True)
    features_dir = output_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)

    feature_paths: Dict[str, Path] = {}
    for feature_name, file_paths in mapping.items():
        summaries = [file_summaries[p] for p in file_paths if p in file_summaries]
        page = generator.generate_feature_page(feature_name, summaries)
        file_name = generator.feature_filename(feature_name)
        page_path = features_dir / file_name
        page_path.write_text(page, encoding="utf-8")
        feature_paths[feature_name] = page_path

    # Keep the consolidated overview next to the site index so links resolve cleanly.
    # This matches the user's expectation: docs/PROJECT_OVERVIEW.md lives alongside docs/features/.
    (output_dir / "PROJECT_OVERVIEW.md").write_text(
        (project_overview or "").strip() + "\n",
        encoding="utf-8",
    )

    index_lines: List[str] = []
    index_lines = []
    index_lines.append("# Documentation\n")
    index_lines.append("## Global Overview\n")
    index_lines.append("This site is generated from semantic file summaries and a project overview.\n")
    index_lines.append("\n## Project Overview\n")
    index_lines.append("The consolidated overview is available at [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).\n")
    index_lines.append("\n## Features\n")
    for feature_name in sorted(feature_paths.keys(), key=lambda s: s.lower()):
        slug = generator.feature_filename(feature_name)
        index_lines.append(f"- [{feature_name}](features/{slug})")

    (output_dir / "index.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")

    return feature_paths
