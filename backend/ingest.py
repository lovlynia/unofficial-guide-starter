"""
Embedding + vector store ingestion for The Unofficial Guide.

Reads the scraped documents, chunks them (chunker.py), embeds each chunk with
a local sentence-transformers model, and stores them in a persistent ChromaDB
collection. Runs entirely locally — no API key, no rate limits.

Embedding model: all-MiniLM-L6-v2 (384-dim, fast, strong on short English text
like reviews — a good fit for this review-heavy corpus).

Run:
    python ingest.py
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from chunker import chunk_documents

CHROMA_DIR = Path(__file__).resolve().parent / "chroma_db"
COLLECTION_NAME = "ccsu_guide"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_collection(reset: bool = False):
    """Return the Chroma collection, creating it if necessary."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:  # noqa: BLE001 - collection may not exist yet
            pass
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def ingest() -> None:
    """Chunk all documents and (re)build the vector store."""
    print("Chunking documents...")
    chunks = chunk_documents()
    print(f"  {len(chunks)} chunks ready")

    print(f"Building Chroma collection '{COLLECTION_NAME}' "
          f"(embedding with {EMBEDDING_MODEL})...")
    collection = get_collection(reset=True)

    ids = [f"{c.source_file}-{c.index}" for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]

    # Add in batches so embedding stays memory-friendly.
    batch_size = 128
    for start in range(0, len(documents), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"  embedded {min(end, len(documents))}/{len(documents)}")

    print(f"\nDone. Vector store persisted at {CHROMA_DIR}")
    print(f"Total vectors: {collection.count()}")


if __name__ == "__main__":
    ingest()
