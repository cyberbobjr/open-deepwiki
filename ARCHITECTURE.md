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
        GraphBuild["services.indexing._build_project_graph"]
        Heuristics["services.indexing._index_heuristic_summaries"]
        Ppl["core.documentation.pipeline.run_documentation_pipeline"]
    end
    
    %% Documentation Logic
    subgraph DocLogic [Documentation Logic]
        UC["GenerateDocumentationUseCase.execute()"]
        SemSum["SemanticSummarizer (LLM/Agentic)"]
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
    
    %% Job Flow
    Job -->|"1. Scan"| Indexer
    Indexer -->|"List[CodeBlock]"| ICB
    
    Job -->|"2. Graph"| GraphBuild
    GraphBuild -.-> GraphBuilder
    
    Job -->|"3. Heuristics"| Heuristics
    Heuristics -->|"List[CodeBlock]"| IFS
    
    Job -->|"4. Semantic Pipeline"| Ppl
    Ppl --> UC
    
    UC --> SemSum
    SemSum -->|"summarize_file()"| SemSum
    SemSum -->|"detect_features_hybrid()"| SemSum
    SemSum -->|"map_files_to_features()"| SemSum
    SemSum -->|"summarize_module(context)"| SemSum
    SemSum -->|"create_project_overview()"| SemSum
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
        -_scan_and_index_codebase()
        -_build_project_graph()
        -_index_heuristic_summaries()
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

### Flux d'Exécution (Indexation Complète - `run_index_directory_job`)

```mermaid
sequenceDiagram
    participant Job as services.indexing
    participant Scan as CodebaseScanner
    participant Vector as VectorIndex
    participant Graph as GraphStore
    participant Pipeline as DocumentationPipeline

    Note over Job: 1. Scan & Index Code
    Job->>Scan: scan(directory)
    Scan-->>Job: List[CodeBlock]
    
    Job->>Vector: index_code_blocks(blocks)
    Vector-->>Job: Embeddings Created
    
    Note over Job: 2. Build Dependency Graph
    Job->>Graph: rebuild(project, blocks)
    Job->>Graph: overview_text(project)
    Graph-->>Job: Graph Overview
    
    Note over Job: 3. Heuristic Summaries (Optional)
    opt include_file_summaries
        Job->>Vector: index_file_summaries(blocks)
        Vector-->>Job: summaries_map
    end
    
    Note over Job: 4. Semantic Documentation
    Job->>Pipeline: run_documentation_pipeline(project_name, indexed_path, precomputed_summaries)
    Pipeline-->>Job: Documentation Generated & Indexed
    
    Note over Job: 5. Finalize
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
        +summarize_module(name, summaries) -> ModuleMetadata
        +create_project_overview(dir, modules)
        +detect_features_hybrid(modules, entrypoints, vision, graph)
        +map_files_to_features(files, features, graph_deps)
        +generate_feature_narrative(feature, summaries)
        +generate_feature_technical_deep_dive(feature, summaries, facet)
    }

    class DocumentationSiteGenerator {
        +build_site(output_dir, overview, modules, narratives, deep_dives, mappings)
        +feature_filename(name)
    }

    class ModuleMetadata {
        +string short_title
        +string category
        +string summary
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
    
    SemanticSummarizer ..> ModuleMetadata : produces
    SemanticSummarizer --> LLMProvider
    DocumentationSiteGenerator --> LLMProvider
```

### Flux d'Exécution (Pipeline Documentaire Hybride)

```mermaid
sequenceDiagram
    participant Pipeline as pipeline.py
    participant UC as GenerateDocumentationUseCase
    participant Reader as CodebaseReader
    participant Summarizer as SemanticSummarizer
    participant SiteGen as DocumentationSiteGenerator (IO)
    participant Indexer as VectorStoreIndexer

    Pipeline->>UC: execute(DocumentationRequest)
    
    %% 1. Semantic File Summaries
    UC->>Reader: read_files()
    loop For each file
        UC->>Summarizer: summarize_file(code)
        Summarizer-->>UC: File Summary (Arcitectural Role)
    end
    
    %% 2. Feature Extraction & Hybrid Discovery (Moved Up)
    opt If Site Generation Enabled
        Note over UC: Gather Hybrid Context (Vision, Entrypoints, Graph)
        UC->>Reader: Read README
        
        UC->>Summarizer: detect_features_hybrid(files_by_folder, entrypoints, vision, graph)
        Summarizer-->>UC: Feature List (Functional)
        
        UC->>Summarizer: map_files_to_features(files, features, graph_deps)
        Summarizer-->>UC: Mapping {feature: [files]}
    end

    %% 3. Module Summaries & Metadata (Context-Aware)
    loop For each module
        UC->>Summarizer: summarize_module(file_summaries, related_features)
        Summarizer-->>UC: ModuleMetadata (Category + Summary + Backlinks)
        opt Indexing
            UC->>Indexer: index_module_summary()
        end
    end
    
    %% 4. Project Overview
    UC->>Summarizer: create_project_overview(modules)
    Summarizer-->>UC: Project Overview
    
    %% 5. Feature Pages Generation
    opt If Site Generation Enabled
        loop For each Feature
            %% 5a. Functional Narrative ("The Story")
            UC->>Summarizer: generate_feature_narrative(feature, summaries)
            Summarizer-->>UC: Narrative Markdown
            
            %% 5b. Technical Deep Dives (Facets)
            UC->>Summarizer: generate_feature_technical_deep_dive(..., "ARCHITECTURE_LIFECYCLE")
            Summarizer-->>UC: Architecture Deep Dive
            
            UC->>Summarizer: generate_feature_technical_deep_dive(..., "DATA_FLOW_TRANSFORMATIONS")
            Summarizer-->>UC: Data Flow Deep Dive
            
            opt Indexing
                UC->>Indexer: index_feature_page(Narrative)
            end
        end

        %% 6. Persistence (Nested Site Generation)
        UC->>SiteGen: build_site(overview, modules, narratives, deep_dives, ...)
        SiteGen->>SiteGen: Generate toc.json (nested modules)
        SiteGen-->>UC: Saved Files
    end
```

## Philosophie de Documentation : "Fluidité & Deep Linking"

Pour éviter la séparation stricte entre "Récit Fonctionnel" et "Implémentation Technique", l'architecture suit une approche de **Tissage** :

1. **Feature comme Conteneur** : Les modules ne sont pas isolés dans une section annexe, mais présentés comme des "Détails d'Implémentation" directement sous la Feature qu'ils servent.
2. **Context Injection** : Lors de la génération du résumé d'un module, le LLM reçoit la liste des Features auxquelles ce module participe. Il génère alors un bloc `> [!NOTE]` explicite liant la technique au fonctionnel.
3. **Navigation Bidirectionnelle** : L'utilisateur peut naviguer de la Story vers le Module (via le TOC imbriqué et les liens contextuels) et du Module vers la Story (via les backlinks générés en début de fichier).

---

## Détail : Moteur de Recherche & RAG (Query)

Cette section décrit comment une requête utilisateur est traitée via le flux streaming SSE, enrichie par le contexte hybride, et exécutée par l'agent.

### Diagramme de Classes (Query Pipeline)

```mermaid
classDiagram
    class AskRouter {
        <<Controller>>
        +ask_stream(request)
        -_condense_query()
        -_retrieve_context()
        -_fetch_session_history()
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
    
    class RetrievalCache {
        <<In-Memory>>
        +get(key)
        +set(key, value)
    }

    AskRouter --> SqliteCheckpointSaver : Load History
    AskRouter --> GraphEnrichedRetriever : Fetch Code Context
    AskRouter --> VectorStore : Fetch Docs/Overview
    AskRouter --> RetrievalCache : Dedup
    AskRouter --> CodebaseAgent : Threaded Execution
```

### Flux d'Exécution (Requête SSE & Récupération Hybride)

```mermaid
sequenceDiagram
    participant User
    participant API as API (/ask/stream)
    participant Hist as Checkpointer (SQLite)
    participant LLM as LLM (OpenAI)
    participant Ret as GraphEnrichedRetriever
    participant VDB as ChromaDB (Docs/Code)
    participant Agent as CodebaseAgent (Thread)

    User->>+API: POST /ask/stream (JSON Payload)
    
    %% 1. History & Condensation
    API->>Hist: fetch_session_history(session_id)
    Hist-->>API: Messages List
    API->>LLM: _condense_query(question, history)
    LLM-->>API: Standalone Query
    
    API-->>User: SSE event: meta {query, session_id}

    %% 2. Hybrid Retrieval
    rect rgb(240, 248, 255)
        Note over API: _retrieve_context()
        
        par Code Retrieval
            API->>Ret: get_relevant_documents(standalone_query)
            Ret->>VDB: search(type=java_method)
            Ret->>Ret: Follow 'calls' graph deps
            Ret-->>API: Enriched Code Blocks
        and Docs Retrieval
            API->>VDB: search(type=generated_markdown)
            VDB-->>API: Markdown Pages
        and Overview Retrieval
            API->>VDB: search(type=project_overview)
            VDB-->>API: Project Overview
        end
        
        API->>API: Deduplicate against History
    end

    API-->>User: SSE event: context {blocks}

    %% 3. Agent Execution (Threaded)
    API->>Agent: Create Agent (System Prompt + Tools)
    API->>Agent: Thread.start(agent.invoke)

    loop Reasoning Loop (Async Queue)
        Agent->>LLM: Think / Tool Call
        opt Tool Execution
            LLM-->>Agent: Call Tool (vector_search, graph_overview)
            Agent->>Agent: Execute Tool
        end
        LLM-->>Agent: Token
        Agent-->>API: Queue.put(Token)
        API-->>User: SSE event: token {delta}
    end
    
    Agent-->>API: Final Answer
    API-->>User: SSE event: done {answer}
    API-->>-User: Close Stream
```

### Stratégie de Récupération "Hybride"

Le système ne se contente pas de chercher du code. La méthode `_retrieve_context` agrège trois sources distinctes pour donner une vision complète à l'agent :

1. **Code Enriched** (`GraphEnrichedRetriever`) :
    * Recherche vectorielle sur les chunks de code (`java_method`).
    * **Graph Walk** : Si un chunk contient des métadonnées `calls`, le retriever va automatiquement chercher le code des fonctions appelées (via `method_docs_map`) pour fournir le contexte d'exécution immédiat.
2. **Documentation Sémantique** :
    * Recherche vectorielle sur les fichiers Markdown générés (`generated_markdown`), permettant de récupérer les explications fonctionnelles ("Features") liées à la requête.
3. **Project Overview** :
    * Injection systématique (ou via recherche) du `project_overview` pour donner le contexte global de l'architecture.

Cette approche permet à l'agent de répondre aussi bien à des questions de bas niveau ("Comment fonctionne cette boucle ?") qu'à des questions de haut niveau ("Quelle est l'architecture de ce module ?").
