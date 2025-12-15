from __future__ import annotations

from typing import Dict, List

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.parsing.java_parser import JavaMethod


def index_java_methods(methods: List[JavaMethod], vectorstore: Chroma) -> Dict[str, Document]:
    """Index Java methods into the vector store.

    Notes:
    - Chroma metadata must contain primitive types.
    - `calls` is serialized as a comma-separated string (tests rely on this).
    """

    documents: List[Document] = []
    method_docs_map: Dict[str, Document] = {}

    for method in methods:
        content_parts = [
            f"Signature: {method.signature}",
            f"Type: {method.type}",
        ]

        if method.javadoc:
            content_parts.append(f"Documentation: {method.javadoc}")

        if method.calls:
            content_parts.append(f"Calls: {', '.join(method.calls)}")

        content_parts.append(f"Code:\n{method.code}")

        content = "\n\n".join(content_parts)

        calls_serialized = ", ".join(sorted(method.calls))

        doc = Document(
            page_content=content,
            metadata={
                "id": method.id,
                "signature": method.signature,
                "type": method.type,
                "calls": calls_serialized,
                "has_javadoc": method.javadoc is not None,
            },
        )

        documents.append(doc)
        method_docs_map[method.id] = doc

    vectorstore.add_documents(documents)

    return method_docs_map
