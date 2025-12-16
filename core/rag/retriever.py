from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_chroma import Chroma
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field


class GraphEnrichedRetriever(BaseRetriever):
    """Retriever that enriches results by following `calls` metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Chroma
    k: int = 4
    project: Optional[str] = None
    method_docs_map: Dict[str, Document] = Field(default_factory=dict)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        search_filter: Optional[Dict[str, Any]] = {"doc_type": "java_method"}
        if self.project is not None:
            # Chroma's `where` expects either a single field predicate or a single
            # boolean operator (e.g. {"$and": [...]}) when combining predicates.
            search_filter = {
                "$and": [
                    {"doc_type": "java_method"},
                    {"project": self.project},
                ]
            }

        try:
            initial_docs = self.vectorstore.similarity_search(query, k=self.k, filter=search_filter)
        except TypeError:
            initial_docs = self.vectorstore.similarity_search(query, k=self.k)

        enriched_docs: List[Document] = []
        seen_ids = set()

        for doc in initial_docs:
            doc_key = (doc.metadata or {}).get("scoped_id") or (doc.metadata or {}).get("id")
            if doc_key and doc_key not in seen_ids:
                enriched_docs.append(doc)
                seen_ids.add(doc_key)

            calls_meta: Any = doc.metadata.get("calls", [])
            if isinstance(calls_meta, str):
                calls = [c.strip() for c in calls_meta.split(",") if c.strip()]
            else:
                calls = list(calls_meta or [])

            for call_name in calls:
                for method_id, dep_doc in self.method_docs_map.items():
                    if call_name.lower() in dep_doc.metadata.get("signature", "").lower():
                        dep_key = (dep_doc.metadata or {}).get("scoped_id") or (dep_doc.metadata or {}).get("id") or method_id
                        if dep_key not in seen_ids:
                            enriched_doc = Document(
                                page_content=f"[DEPENDENCY] {dep_doc.page_content}",
                                metadata={
                                    **(dep_doc.metadata or {}),
                                    "is_dependency": True,
                                    "called_from": (doc.metadata or {}).get("scoped_id")
                                    or (doc.metadata or {}).get("id"),
                                },
                            )
                            enriched_docs.append(enriched_doc)
                            seen_ids.add(dep_key)

        return enriched_docs

    def get_relevant_documents(self, query: str) -> List[Document]:
        return self.invoke(query)
