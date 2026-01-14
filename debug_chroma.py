import os

from dotenv import load_dotenv
from langchain_chroma import Chroma

from core.rag.embeddings import create_embeddings

load_dotenv()

from config import apply_config_to_env, load_config


def inspect():
    try:
        config = load_config("open-deepwiki.yaml")
        apply_config_to_env(config)
    except Exception as e:
        print(f"Config load failed: {e}")

    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "code_blocks")
    base_url = os.getenv("OPENAI_EMBEDDING_API_BASE")
    
    print(f"Checking Chroma at {persist_dir}, collection={collection_name}")
    
    embeddings = create_embeddings(base_url)
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )
    
    # Try multiple ID variations for project overview
    ids_to_check = [
        "test::project::overview",
        "project::overview", 
    ]
    
    print("\n--- Checking specific IDs ---")
    try:
        results = vectorstore.get(ids=ids_to_check, include=["metadatas", "documents"])
        for i, id_ in enumerate(results["ids"]):
            print(f"Found ID: {id_}")
            print(f"Metadata: {results['metadatas'][i]}")
    except Exception as e:
        print(f"Error fetching specific IDs: {e}")

    print("\n--- Checking all metadatas (limit 20) ---")
    try:
        # Inspect a few items to see structure
        all_res = vectorstore.get(limit=20, include=["metadatas"])
        for m in all_res["metadatas"]:
            print(m)
    except Exception as e:
        print(f"Error fetching all: {e}")

if __name__ == "__main__":
    inspect()
