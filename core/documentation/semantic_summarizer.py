from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from langchain_core.messages import (BaseMessage, HumanMessage, SystemMessage,
                                     ToolMessage)
from pydantic import BaseModel, Field

from core.ports.llm_port import LLMProvider
from core.services.codebase_reader import CodebaseReader

logger = logging.getLogger(__name__)

MERMAID_RULES_PROMPT = (
    "MERMAID RULES:\n"
    "- **Structure**: Use `graph TD` or `sequenceDiagram` as appropriate. If `classDiagram` is requested, follow strict class naming.\n"
    "- **Strictly use NEWLINES**: Every node, edge, and subgraph definition MUST be on a new line.\n"
    "- **Safe IDs**: Node/Class IDs must be alphanumeric only (e.g. `MyNode`, `UserService`). NO spaces or special characters in IDs.\n"
    "- **Quote Labels (Graph)**: In `graph TD`, ALWAYS use double quotes for labels: `id[\"Label text\"]`.\n"
    "- **Class Diagram**: Class names must be PascalCase alphanumeric (e.g. `SpringBoot`). NO spaces/quotes in class names. Relationship labels can be quoted.\n"
    "- **Subgraph Syntax**: `subgraph IdSimple [\"My Title\"]`. The ID must be simple alphanumeric (no spaces). Title in quotes.\n"
    "- **Sequence Syntax**: `participant A as \"Label\"`. Do not use `participant A(Label)`.\n"
    "- **Edges**: Connect specific nodes (`A --> B`), NOT subgraphs directly.\n"
    "- **Verify Syntax**: Ensure the output is valid Mermaid code.\n"
)


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


def _clean_llm_response(text: str) -> str:
    """Clean markdown code fences from the LLM response."""
    cleaned = text.strip()
    # Remove leading ```markdown or ```
    if cleaned.startswith("```markdown"):
        cleaned = cleaned[len("```markdown"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    
    # Remove trailing ```
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
        
    return cleaned


def _extract_file_titles_from_summaries(summaries: Sequence[str]) -> List[str]:
    """Extract file identifiers from file summary markdown."""
    results: List[str] = []
    for summary in summaries:
        first_line = (summary or "").lstrip().splitlines()[0] if (summary or "").strip() else ""
        if first_line.startswith("## "):
            results.append(first_line[3:].strip())
    return [x for x in results if x]


class ModuleMetadata(BaseModel):
    """Metadata for a system module."""
    short_title: str = Field(description="Max 3-4 words clear title for navigation (e.g. 'User Auth').")
    category: str = Field(description="Architectural Layer: 'Domain', 'Infrastructure', 'Entrypoints', 'Core', 'Utils', 'Config'.")
    summary: str = Field(description="The architectural summary content in Markdown.")


class FeatureList(BaseModel):
    """List of features extracted from project overview."""
    features: List[str] = Field(description="List of 5-10 primary functional topics (features).")


class FileFeatureAssignment(BaseModel):
    """Assignment of a file to a feature."""
    file_path: str = Field(description="The file path being classified.")
    feature: str = Field(description="The assigned feature name.")


class BatchClassification(BaseModel):
    """Collection of file-to-feature assignments."""
    assignments: List[FileFeatureAssignment] = Field(description="List of file classifications.")


class SemanticSummarizer:
    """Service for generating semantic summaries of code artifacts using an LLM (Agentic)."""

    def __init__(self, llm: LLMProvider, reader: CodebaseReader):
        self.llm = llm
        self.reader = reader
        self.known_files: List[Path] = []

    def set_known_files(self, files: List[Path]) -> None:
        """Register the list of known source files for resolution."""
        self.known_files = sorted(list(files), key=lambda p: str(p))

    def _read_file_tool(self, file_path: str) -> str:
        """
        Read the content of a file to gain more context.
        Args:
            file_path: Relative or absolute path to the file. Can also be a partial name or class name.
        """
        try:
            logger.info(f"Tool '_read_file_tool' called with: {file_path}")
            target = Path(file_path)
            if not target.is_absolute():
                # 1. Try direct resolution
                candidate = self.reader.root_dir / target
                if candidate.exists() and candidate.is_file():
                    content = self.reader.read_file_content(candidate)
                    logger.info(f"Direct resolution successful for: {candidate}")
                    return _truncate_middle(content, max_chars=10_000)
                
                # 2. Smart Search (Heuristic)
                # If direct resolution failed, try to find by name in known_files
                if self.known_files:
                    search_term = target.name
                    # Heuristic: if it looks like a package/namespace 'com.foo.Bar', take 'Bar'
                    # We check if there are dots but NO path separators
                    if "." in file_path and not (set("/\\") & set(file_path)):
                         search_term = file_path.split(".")[-1]
                    
                    search_lower = search_term.lower()

                    # Priority 1: Exact Stem Match (e.g. 'User' matches 'User.ts', 'User.java', 'src/User.go')
                    # We look for files where the filename without extension equals the search term
                    matches = [
                        p for p in self.known_files
                        if p.stem.lower() == search_lower
                    ]

                    # Priority 2: Fallback to loose containment if no stem match
                    if not matches:
                        matches = [
                            p for p in self.known_files 
                            if search_lower in p.name.lower()
                        ]

                    if len(matches) == 1:
                        # Found exactly one candidate -> read it
                        resolved = matches[0]
                        content = self.reader.read_file_content(resolved)
                        logger.info(f"Smart search resolved '{file_path}' to '{resolved}'")
                        return (
                            f"/* Resolved '{file_path}' to '{resolved.relative_to(self.reader.root_dir)}' */\n\n"
                            + _truncate_middle(content, max_chars=10_000)
                        )
                    elif len(matches) > 1:
                        # Ambiguous - try to filter by similarity to the requested path structure if possible, 
                        # otherwise strictly list candidates.
                        # If we have too many matches, just returning the list is better than guessing wrong.
                        candidates = [str(p.relative_to(self.reader.root_dir)) for p in matches[:5]]
                        logger.warning(f"Ambiguous reference '{file_path}'. Matches: {candidates}")
                        return f"Ambiguous reference '{file_path}'. Found {len(matches)} matches. Did you mean:\n- " + "\n- ".join(candidates)
            
            logger.warning(f"File not found: {file_path}")
            return f"File not found: {file_path}. (Checked direct path and smart search)"
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
            return f"Error reading file {file_path}: {e}"

    def summarize_file(self, file_path: Path, code: str, max_chars: int = 40_000) -> str:
        """Generate a semantic file-level summary (Agentic)."""
        rel_name = str(file_path)
        trimmed = (code or "").strip()
        if not trimmed:
            return f"## {rel_name}\n\n_Empty file._\n"

        code_for_llm = _truncate_middle(trimmed, max_chars=max_chars)

        system = SystemMessage(
            content=(
                "You are a senior software architect creating a deep and detailed documentation. "
                "Your goal is to explain the *intent* and *architecture* of the code, not just describe it. "
                "You have access to a tool `read_file` to read other files if crucial for understanding context. "
                "Use the tool only if strictly necessary. "
                "Final Output MUST be clean Markdown starting with '## <filename>'. "
                "Do not include fenced code blocks in specific sections unless requested."
            )
        )

        human = HumanMessage(
            content=(
                "Analyze this source file and produce a detailed summary.\n\n"
                "Requirements:\n"
                "1. **Semantic Role**: One concise line identifying the architectural role (e.g., 'Core Context Port', 'Data Entity', 'Orchestration Service').\n"
                "2. **Strategic Responsibility**: Explain *WHY* this file exists. What business problem does it solve?\n"
                "3. **Business Invariants**: List 2-3 non-negotiable rules or logic enforced by this file (e.g., 'A user must always have an email').\n"
                "4. **Key Features**: 3-5 bullet points focusing on capabilities.\n\n"
                "Style Rules:\n"
                "- Use 'Wikipedia' style: informative, high-level, intent-focused.\n"
                "- Use callouts like `> [!NOTE]` or `> [!IMPORTANT]` for critical architectural details.\n"
                "- Remove low-level details (variables, imports).\n\n"
                f"File: {rel_name}\n\n"
                "Code:\n"
                f"{code_for_llm}"
            )
        )

        tools = [self._read_file_tool]
        messages: List[BaseMessage] = [system, human]
        
        # Simple ReAct Loop (Max 3 turns)
        max_turns = 3
        
        try:
            for _ in range(max_turns):
                response = self.llm.invoke_with_tools(messages, tools)
                messages.append(response)
                
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        # naive tool execution
                        if tool_call["name"] == "_read_file_tool":
                            # LangChain tool call args are dict
                            args = tool_call["args"]
                            path_arg = args.get("file_path")
                            tool_result = self._read_file_tool(path_arg)
                            
                            messages.append(ToolMessage(
                                content=tool_result,
                                tool_call_id=tool_call["id"]
                            ))
                else:
                    # No tool call, implicit finish (or we could force a final answer tool)
                    raw_result = getattr(response, "content", "")
                    if isinstance(raw_result, str):
                        result = _clean_llm_response(raw_result)
                         # Validate output format
                        if not result.strip():
                             continue # Retry or fail?
                        
                        if not result.lstrip().startswith("##"):
                            return f"## {rel_name}\n\n{result.strip()}\n"
                        return result.strip() + "\n"
                    # If content is empty but no tool calls, strange.
                    return f"## {rel_name}\n\n_Agent returned empty response._\n"
            
            # If loop exhausted
            return f"## {rel_name}\n\n_Analysis incomplete (max turns reached)._\n"

        except Exception as e:
            return (
                f"## {rel_name}\n\n"
                f"_LLM summarization failed: {type(e).__name__}: {e}_\n\n"
                "Features:\n"
                "- (unavailable)\n"
            )

    def summarize_module(
        self,
        module_name: str,
        file_summaries: List[str],
        max_chars: int = 60_000,
    ) -> ModuleMetadata:
        """Generate a module/folder summary with architectural focus."""
        summaries = [s.strip() for s in (file_summaries or []) if (s or "").strip()]

        if not summaries:
            # Fallback for empty modules
            return ModuleMetadata(
                short_title=Path(module_name).name,
                category="Utils",
                summary=f"# {module_name}\n\n_No files found to summarize._\n"
            )

        joined = "\n\n".join(summaries)
        joined = _truncate_middle(joined, max_chars=max_chars)

        system = SystemMessage(
            content=(
                "You are a software architect documenting a system module. "
                "Focus on the module's BOUNDARIES (what goes in/out) and its internal collaboration. "
                "You must classify the module into a category (e.g. Core, Infrastructure, API, Utils). "
                "Start the summary with a H1 Title: `# <ModuleName>`. "
                "Return clean Markdown with Mermaid diagrams for the summary field.\n"
                f"{MERMAID_RULES_PROMPT}"
            )
        )

        human = HumanMessage(
            content=(
                "Create an architectural summary for this module and categorize it.\n\n"
                "Structure for Summary:\n"
                "1. **Purpose and Scope**: What does this module do? What is its role in the system?\n"
                "2. **Module Boundaries**: Identify Entry Points (Public APIs) and External Dependencies.\n"
                "3. **Collaboration Logic**: How do the files inside work together?\n"
                "4. **Components**: Brief list of key entities.\n"
                "5. **Architecture Diagrams**:\n"
                "   - `classDiagram`: Show structure.\n"
                "   - `sequenceDiagram`: Show a key data flow entering the boundary and being processed.\n\n"
                f"Folder: {module_name}\n\n"
                "File summaries:\n"
                f"{joined}"
            )
        )

        try:
            result: ModuleMetadata = self.llm.invoke_structured([system, human], ModuleMetadata)
            # Clean up the markdown in the summary field
            result.summary = _clean_llm_response(result.summary)
            stripped = result.summary.lstrip()
            
            # Determine the display title (Short Title or Fallback)
            display_title = result.short_title.strip() if result.short_title else Path(module_name).name
            
            # Force the header to match the display title
            lines = stripped.splitlines()
            if lines and (lines[0].startswith("# ") or lines[0].startswith("## ")):
                # Replace existing header
                lines[0] = f"# {display_title}"
                result.summary = "\n".join(lines)
            else:
                # Prepend header
                result.summary = f"# {display_title}\n\n{result.summary}"
            
            return result
        except Exception as e:
            # Fallback
            short = Path(module_name).name
            return ModuleMetadata(
                short_title=short,
                category="Uncategorized",
                summary=f"# {short}\n\n_LLM module summary failed: {e}_\n"
            )

    def create_project_overview(
        self,
        root_dir: Path,
        module_summaries: Dict[str, str],
        max_chars: int = 60_000,
    ) -> str:
        """Generate a 'North Star' project overview."""
        # Aggregate module summaries
        joined_modules = "\n\n".join(f"### Module {k}\n{v}" for k, v in module_summaries.items())
        context = _truncate_middle(joined_modules, max_chars=max_chars)
        
        system = SystemMessage(
            content=(
                "You are the Lead Architect. Create the 'North Star' document for this project. "
                "Analyze the Design Philosophy (e.g. Clean Architecture, Event-Driven). "
                "Use Mermaid `subgraph` to group modules by logical layers (Core, Infrastructure, Application).\n"
                "Return clean Markdown.\n"
                f"{MERMAID_RULES_PROMPT}"
            )
        )
        
        human = HumanMessage(
            content=(
                f"Create a File describing the Project Overview for '{root_dir.name}'.\n\n"
                "Requirements:\n"
                "1. **Vision & Purpose**: The high-level business value.\n"
                "2. **Design Philosophy**: Analyze the architectural patterns used.\n"
                "   - Mention Clean Architecture, Hexagonal, etc. if detected.\n"
                "3. **System Architecture Diagram** (Mermaid):\n"
                "   - Use `subgraph` to group modules logically (e.g., 'Core', 'Infrastructure', 'Adapters').\n"
                "   - Show dependencies between groups.\n"
                "4. **Key Modules**: Brief strategic summary of top modules.\n\n"
                "MODULE SUMMARIES:\n"
                f"{context}"
            )
        )
        
        try:
            result_obj = self.llm.invoke([system, human])
            if not result_obj:
                return f"# {root_dir.name}\n\n_Empty overview generated._\n"
            
            result = _clean_llm_response(str(result_obj.content)) if hasattr(result_obj, "content") else _clean_llm_response(str(result_obj))
            
            return result.strip() + "\n"
        except Exception as e:
            logger.error(f"Project overview generation failed: {e}", exc_info=True)
            return (
                f"# {root_dir.name}\n\n"
                f"_LLM overview generation failed: {type(e).__name__}: {e}_\n"
            )

    def extract_features_from_modules(
        self,
        module_summaries: Dict[str, str],
        max_chars: int = 60_000,
    ) -> FeatureList:
        """Extract a refined list of features from module summaries."""
        # Aggregate module summaries
        joined_modules = "\n\n".join(f"### Module {k}\n{v}" for k, v in module_summaries.items())
        context = _truncate_middle(joined_modules, max_chars=max_chars)

        system = SystemMessage(
            content=(
                "You are a Product Owner. "
                "Identify the high-level CROSS-CUTTING Features provided by the system. "
                "Ignore internal technical details (like 'Utils' or 'Helpers'). "
                "Focus on User Flows and Business Capabilities."
            )
        )
        human = HumanMessage(
            content=(
                "Extract 5-10 primary Features from these summaries.\n"
                "Rules:\n"
                "- Feature Name should be Functional (e.g., 'User Authentication' NOT 'AuthModule').\n"
                "- Focus on what the system DOES for the user/business.\n"
                "- Avoid implementation details.\n\n"
                "SUMMARIES:\n"
                f"{context}"
            )
        )

        structured_llm = self.llm.invoke_structured([system, human], FeatureList)
        return structured_llm

    def map_files_to_features(
        self,
        file_summaries: Mapping[str, str],
        feature_list: FeatureList,
        batch_size: int = 10,
    ) -> Dict[str, List[str]]:
        """Classify files into the extracted features."""
        features = [f.strip() for f in feature_list.features if (f or "").strip()]
        if not features:
            # Fallback if LLM returned nothing
            features = ["General"]

        # Deduplicate features list
        seen = set()
        unique_features = []
        for f in features:
            if f not in seen:
                unique_features.append(f)
                seen.add(f)
        features = unique_features

        files = [(k, v) for k, v in (file_summaries or {}).items() if (k or "").strip()]
        batches: List[List[Tuple[str, str]]] = []
        for i in range(0, len(files), batch_size):
            batches.append(files[i : i + batch_size])

        assignments: Dict[str, str] = {}

        system = SystemMessage(
            content=(
                "You are a senior software analyst performing zero-shot classification. "
                "Assign each file to exactly ONE feature from the provided list. "
            )
        )

        for batch in batches:
            payload_items: List[Dict[str, str]] = []
            for path, summary in batch:
                payload_items.append(
                    {
                        "file_path": path,
                        "summary": _truncate_middle(summary or "", max_chars=6_000),
                    }
                )

            human = HumanMessage(
                content=(
                    "Classify each file into the single most relevant feature.\n\n"
                    "FEATURE LIST:\n"
                    f"{json.dumps(features, ensure_ascii=False)}\n\n"
                    "FILES (JSON array of objects with fields 'file_path' and 'summary'):\n"
                    f"{json.dumps(payload_items, ensure_ascii=False)}\n\n"
                    "Classify all files."
                )
            )

            try:
                result: BatchClassification = self.llm.invoke_structured([system, human], BatchClassification)
                for assignment in result.assignments:
                    if assignment.feature in features:
                       assignments[assignment.file_path] = assignment.feature
                    else:
                        assignments[assignment.file_path] = features[0]
            except Exception:
                # Fallback on error
                for path, _ in batch:
                    assignments[path] = features[0]

        default_feature = features[0]
        for file_path, _summary in files:
            if file_path not in assignments:
                assignments[file_path] = default_feature

        by_feature: Dict[str, List[str]] = {f: [] for f in features}
        for file_path, feature in sorted(assignments.items(), key=lambda kv: kv[0]):
            by_feature.setdefault(feature, []).append(file_path)

        return by_feature

    def generate_feature_page(
        self,
        feature_name: str,
        related_file_summaries: Sequence[str],
        max_chars: int = 60_000,
    ) -> str:
        """Generate a feature page focusing on the Functional Narrative."""
        name = (feature_name or "").strip() or "Feature"
        summaries = [s.strip() for s in (related_file_summaries or []) if (s or "").strip()]

        related_titles = _extract_file_titles_from_summaries(summaries)
        logger.info(f"Generating feature page for: '{name}'. Found {len(related_titles)} related files: {related_titles}")

        if not related_titles and summaries:
             logger.warning(f"Feature '{name}': Summaries found but no file titles extracted. Check summary format.")
        elif not summaries:
             logger.warning(f"Feature '{name}': No file summaries provided.")

        joined = _truncate_middle("\n\n".join(summaries), max_chars=max_chars)

        system = SystemMessage(
            content=(
                "You are a senior software architect creating a deep and detailed documentation. "
                "You are generating a deep and detailed Feature Page. "
                "Tell the 'Story' of this feature: how it works, why it exists, and how data moves through it. "
                "Include granular Mermaid diagrams showing data transformations.\n"
                f"{MERMAID_RULES_PROMPT}"
            )
        )

        human = HumanMessage(
            content=(
                "Write a functional feature narrative.\n\n"
                "Structure:\n"
                "1. **The Story**: A narrative explanation of the user flow (User does X, System executes Y...).\n"
                "2. **Purpose and Scope**: What does this feature do? What is its role in the system?\n"
                "3. **Data Flow**: Describe how data is transformed step-by-step.\n"
                "4. **Participant Components**: Key files involved and their specific duties in this feature.\n"
                "5. **Visual Execution**:\n"
                "   - `sequenceDiagram`: detailed flow showing data objects being passed/transformed.\n"
                "   - `classDiagram`: relevant subset of classes.\n\n"
                "**Primary Participating Modules**: List the top 1-3 modules that drive this feature.\n\n"
                "Deep Linking:\n"
                "- Mention related modules or concepts using `[[Concept Name]]` or standard markdown links if paths are known.\n\n"
                f"Feature: {name}\n\n"
                "File summaries:\n"
                f"{joined}"
            )
        )

        try:
            response_content = self.llm.invoke([system, human])
            # Handle string or message content
            text_content = str(response_content.content) if hasattr(response_content, "content") else str(response_content)
            body = _clean_llm_response(text_content).strip()
            
            if not body:
                body = "_No content generated._"
            
            # Ensure title is present and is H1
            if body.startswith("## "):
                 body = "# " + body[3:]
            elif not body.startswith("# "):
                 body = f"# {name}\n\n{body}"
            
            return body + "\n"
        except Exception as e:
            return f"# {name}\n\n_Feature page generation failed: {e}_\n"
