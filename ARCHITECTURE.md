# Architecture d'Indexation Open DeepWiki

Ce document décrit le fonctionnement interne du système d'indexation multi-langage et de génération de documentation sémantique.

## Vue d'Ensemble

Le système est conçu pour analyser des bases de code hétérogènes (Java, Python, TypeScript), les transformer en vecteurs consultables pour le RAG (Retrieval Augmented Generation), et générer une documentation fonctionnelle progressive via LLM.

### Diagramme de Flux Général (Mermaid)

```mermaid
graph TD
    %% Source Files
    subgraph Sources [Source Code Types]
        J[Java .java]
        P[Python .py]
        TS[TypeScript .ts/.tsx]
    end

    %% Scanning & Parsing (Core)
    subgraph Core [Core Logic]
        Scan["core.scanning.scanner.scan_codebase"]
        F["core.parsing.factory.ParserFactory"]
        
        JP["core.parsing.java_parser.JavaParser"]
        PP["core.parsing.python_parser.PythonParser"]
        TP["core.parsing.typescript_parser.TypeScriptParser"]
        
        LIB[Tree-Sitter Shared Lib]
        
        CB["core.parsing.models.CodeBlock"]
    end

    %% Logic Layers
    subgraph Services [Service Layer]
        Job["services.indexing.run_index_directory_job"]
        Indexer["services.indexing._scan_and_index_codebase"]
        Ppl["core.documentation.pipeline.run_documentation_pipeline"]
    end
    
    %% Documentation Logic
    subgraph DocLogic [Documentation Logic]
        UC["GenerateDocumentationUseCase.execute()"]
        SemSum["SemanticSummarizer (LLM Logic)"]
        SiteGen["DocumentationSiteGenerator (Pure I/O)"]
    end

    %% Storage
    subgraph StorageLayer [Storage Layer]
        ICB["core.rag.indexing.index_code_blocks"]
        IFS["core.rag.indexing.index_file_summaries"]
        IMS["core.rag.indexing.index_module_summary"]
        IPO["core.rag.indexing.index_project_overview"]
        IFP["core.rag.indexing.index_feature_page"]
        
        Emb[OpenAI Embeddings]
        GraphBuilder["core.project_graph.SqliteProjectGraphStore"]
        
        VectorDB[(ChromaDB)]
        GraphDB[(SQLite Graph)]
        FS["FileSystem (Markdown/JSON)"]
    end

    %% Relationships
    J --> Scan
    P --> Scan
    TS --> Scan

    Scan -->|Paths| F
    
    F -->|"get_parser()"| JP
    F -->|"get_parser()"| PP
    F -->|"get_parser()"| TP

    JP -.-> LIB
    PP -.-> LIB
    TP -.-> LIB

    JP -->|"parse()"| CB
    PP -->|"parse()"| CB
    TP -->|"parse()"| CB

    CB -->|"List[CodeBlock]"| Job
    Job --> Indexer
    
    Indexer -->|"List[CodeBlock]"| ICB
    Indexer -->|"List[CodeBlock]"| IFS
    
    Job -.-> GraphBuilder
    
    Job -->|"run_documentation_pipeline()"| Ppl
    Ppl --> UC
    
    UC --> SemSum
    SemSum -->|"summarize_file()"| SemSum
    SemSum -->|"summarize_module()"| SemSum
    SemSum -->|"create_project_overview()"| SemSum
    SemSum -->|"extract_features_from_modules()"| SemSum
    SemSum -->|"map_files_to_features()"| SemSum
    SemSum -->|"generate_feature_page()"| SemSum
    
    UC --> SiteGen
    SiteGen -->|"build_site()"| SiteGen

    ICB -->|Code Embeddings| Emb
    IFS -->|Summary Embeddings| Emb
    IMS -->|Module Embeddings| Emb
    IPO -->|Overview Embeddings| Emb
    IFP -->|Feature Embeddings| Emb
    
    Emb -->|Vectors| VectorDB
    GraphBuilder -->|Nodes/Edges| GraphDB
    
    UC -->|Module Summary| IMS
    IMS -->|Vectors| VectorDB
    
    UC -->|Overview| IPO
    IPO -->|Vectors| VectorDB
    
    UC -->|Feature Page| IFP
    IFP -->|Vectors| VectorDB
    
    SiteGen -->|Markdown Site & Sitemap| FS
```

---

## Détail : Mécanisme de Scan / Indexation (Clean Architecture)

Ce processus utilise un service orchestrateur (`IndexingService`) coordonnant des composants découplés via des interfaces (Ports).

### Diagramme de Classes (Core Indexing)

```mermaid
classDiagram
    class IndexingService {
        +run_index_directory_job()
        +run_regenerate_documentation_job()
    }

    class CodebaseScanner {
        <<interface>>
        +scan()
    }
    class VectorIndex {
        <<interface>>
        +index_code_blocks()
        +index_file_summaries()
        +index_project_overview()
        +index_feature_page()
    }
    class GraphStore {
        <<interface>>
        +rebuild()
        +overview_text()
    }

    IndexingService --> CodebaseScanner
    IndexingService --> VectorIndex
    IndexingService --> GraphStore

    class FileSystemScanner
    class ChromaVectorIndex
    class SqliteProjectGraphStore

    FileSystemScanner ..|> CodebaseScanner
    ChromaVectorIndex ..|> VectorIndex
    SqliteProjectGraphStore ..|> GraphStore
```

### Flux d'Exécution (Indexation Complète)

```mermaid
sequenceDiagram
    participant Job as services.indexing
    participant Scan as CodebaseScanner
    participant Vector as VectorIndex
    participant Graph as GraphStore
    participant Pipeline as DocumentationPipeline

    Job->>Scan: scan(directory)
    Scan-->>Job: List[CodeBlock]
    
    Job->>Vector: index_code_blocks(blocks)
    Vector-->>Job: Embeddings Created
    
    opt include_file_summaries
        Job->>Vector: index_file_summaries(blocks)
    end
    
    Job->>Vector: persist()

    Job->>Graph: rebuild(project, blocks)
    Job->>Graph: overview_text(project)
    Graph-->>Job: Graph Summary
    
    Job->>Pipeline: run_documentation_pipeline(project_name, indexed_path)
    Pipeline-->>Job: Documentation Generated & Indexed
    
    Job->>Job: _finalize_app_state()
```

---

## Détail : Génération de Documentation Markdown (Clean Architecture)

Ce processus a été refactorisé pour suivre les principes de la Clean Architecture. La génération est pilotée par un cas d'utilisation (`GenerateDocumentationUseCase`) et s'appuie sur le module `generation.py`.

### Diagramme de Classes (Composants)

```mermaid
classDiagram
    %% Core Business Logic (Use Case)
    class GenerateDocumentationUseCase {
        +execute(request)
    }

    %% Services (generation.py)
    class SemanticSummarizer {
        +LLMProvider llm
        +CodebaseReader reader
        +summarize_file(path, code)
        +summarize_module(name, summaries)
        +create_project_overview(dir, modules)
        +extract_features_from_modules(module_summaries)
        +map_files_to_features(files, features)
        +generate_feature_page(feature, related_summaries)
    }

    class DocumentationSiteGenerator {
        +build_site(output_dir, overview, modules, features, mappings)
        +feature_filename(name)
    }

    %% Ports (Interfaces)
    class LLMProvider {
        <<interface>>
        +invoke()
        +invoke_structured()
    }
    class DocumentationRepository {
        <<interface>>
        +save_project_overview()
        +save_feature_page()
    }
    class VectorStoreIndexer {
        <<Interface>>
        +index_overview(project, content)
        +index_feature_page(project, feature, content)
        +index_module_summary(project, module, content)
    }

    %% Relationships
    GenerateDocumentationUseCase --> SemanticSummarizer
    GenerateDocumentationUseCase --> DocumentationSiteGenerator
    
    GenerateDocumentationUseCase --> DocumentationRepository
    GenerateDocumentationUseCase --> VectorStoreIndexer
    
    SemanticSummarizer --> LLMProvider
    DocumentationSiteGenerator --> LLMProvider
```

### Flux d'Exécution (Pipeline de Documentation)

```mermaid
sequenceDiagram
    participant Pipeline as pipeline.py
    participant UC as GenerateDocumentationUseCase
    participant Reader as CodebaseReader
    participant Summarizer as SemanticSummarizer
    participant SiteGen as DocumentationSiteGenerator (IO)
    participant Repo as DocumentationRepository
    participant Indexer as VectorStoreIndexer

    Pipeline->>UC: execute(DocumentationRequest)
    UC->>Reader: read_files()
    Reader-->>UC: grouped_files
    UC->>Summarizer: set_known_files(all_files)
    
    %% 1. Semantic File Summaries
    loop For each file
        UC->>Summarizer: summarize_file(code)
        Summarizer-->>UC: File Summary (may use tools)
    end
    
    %% 2. Module Summaries
    loop For each module
        UC->>Summarizer: summarize_module(file_summaries)
        Summarizer-->>UC: Module Summary
        opt Indexing
            UC->>Indexer: index_module_summary(project, module, content)
        end
    end
    
    %% 3. Project Overview
    UC->>Summarizer: create_project_overview(modules)
    Summarizer-->>UC: Project Overview
    UC->>Repo: save_project_overview(overview)
    
    opt Indexing
        UC->>Indexer: index_overview(project, content)
    end
    
    %% 4. Feature Extraction & Generation
    opt If Site Generation Enabled
        UC->>Summarizer: extract_features_from_modules(modules)
        Summarizer-->>UC: Feature List (Structured)
        
        UC->>Summarizer: map_files_to_features(files, features)
        Summarizer-->>UC: Mapping {feature: [files]}
        
        loop For each Feature
            UC->>Summarizer: generate_feature_page(feature, summaries)
            Summarizer-->>UC: Feature Page Content
            UC->>Repo: save_feature_page(feature, content)
            opt Indexing
                UC->>Indexer: index_feature_page(project, feature, content)
            end
        end

        %% 5. Persistence (Site Generation)
        UC->>SiteGen: build_site(overview, modules, features, mapping)
        SiteGen-->>UC: Saved Files & Sitemap
    end
```

---

## Détail : Moteur de Recherche & RAG (Query)

Cette section décrit comment une requête utilisateur est traitée, enrichie par le contexte (RAG), et comment l'Agent répond.

### Diagramme de Classes (Query Pipeline)

```mermaid
classDiagram
    class AskRouter {
        <<Controller>>
        +ask_stream(request)
        -_condense_query()
        -_retrieve_context()
    }

    class GraphEnrichedRetriever {
        <<Retriever>>
        +get_relevant_documents(query)
        -_follow_dependencies(docs)
    }

    class CodebaseAgent {
        <<Agent>>
        +invoke(input)
    }

    class SqliteCheckpointSaver {
        <<Persistence>>
        +get_tuple()
        +put()
    }
    
    class VectorStore {
        <<ChromaDB>>
        +similarity_search()
    }

    AskRouter --> SqliteCheckpointSaver : Load History
    AskRouter --> GraphEnrichedRetriever : Fetch Context
    GraphEnrichedRetriever --> VectorStore : Search
    AskRouter --> CodebaseAgent : Run Reasoning
```

### Flux d'Exécution (Requête RAG)

```mermaid
sequenceDiagram
    participant User
    participant API as API (/ask/stream)
    participant Hist as Checkpointer (SQLite)
    participant LLM as LLM (OpenAI)
    participant Ret as GraphEnrichedRetriever
    participant VDB as ChromaDB
    participant Agent as CodebaseAgent

    User->>+API: Question (SSE Request)
    
    %% 1. Context Loading
    API->>Hist: fetch_session_history(session_id)
    Hist-->>API: Previous Messages

    %% 2. Query Refinement
    API->>LLM: _condense_query(question, history)
    LLM-->>API: Standalone Search Query
    
    %% 3. Retrieval (RAG)
    API->>Ret: get_relevant_documents(standalone_query)
    Ret->>VDB: similarity_search(query, k)
    VDB-->>Ret: Raw Documents (Code & Docs)
    
    opt Dependency Enrichment
        Ret->>Ret: Follow 'calls' metadata
        Ret->>Ret: Fetch dependent methods
    end
    
    Ret-->>API: Enriched Context (Docs + Dependencies)

    %% 4. Agent Execution
    API->>Agent: create_agent(context, system_prompt)
    API->>Agent: invoke(question)
    
    loop Reasoning Loop
        Agent->>LLM: Think / Tool Call
        opt If Tool Needed
            LLM-->>Agent: Call Tool (e.g. graph_neighbors)
            Agent->>Agent: Execute Tool
        end
        LLM-->>Agent: Final Answer Token
        Agent-->>API: Stream Token
        API-->>User: SSE Event (Token)
    end
    
    API-->>-User: SSE Done
```

### Points Clés (Query)

- **Retrieval Hybride** : Le système interroge à la fois les blocs de code, les résumés de fichiers, le Project Overview, et les pages de documentation générées.
- **Enrichissement de Graphe** : `GraphEnrichedRetriever` utilise les métadonnées statiques (`calls`) pour injecter automatiquement le code des dépendances appelées, offrant un contexte plus complet au LLM sans qu'il ait à chercher manuellement.
- **Agent Codebase** : L'agent final dispose d'outils (`vector_search`, `project_graph_overview`) pour explorer davantage si le contexte initial RAG ne suffit pas.
