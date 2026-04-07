"""
scripts/ingest_specs.py

Ingests IATA spec markdown files into ChromaDB.
Run once before starting the agent:

    python scripts/ingest_specs.py

Chunks each spec file by ## section headings.
Stores chunks in a persistent ChromaDB collection: 'iata_specs'.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SPECS_DIR   = Path(__file__).parent.parent / "data" / "specs"
CHROMA_DIR  = Path(__file__).parent.parent / "data" / "chroma_db"
COLLECTION  = "iata_specs"

# Default embedding model — runs locally, no API key needed
EMBED_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Split a markdown file into chunks at every ## heading.
    Each chunk = one section. Returns list of dicts with text + metadata.
    """
    # Split on lines starting with ## (section level)
    sections = re.split(r"\n(?=## )", text)
    chunks = []

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Extract heading as chunk title
        lines = section.splitlines()
        heading = lines[0].lstrip("#").strip() if lines else f"section_{i}"

        chunks.append({
            "text":     section,
            "source":   source,
            "heading":  heading,
            "chunk_id": f"{source}::{i}::{heading}",
        })

    return chunks


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest() -> None:
    # Validate specs directory exists
    if not SPECS_DIR.exists():
        raise FileNotFoundError(f"Specs directory not found: {SPECS_DIR}")

    spec_files = list(SPECS_DIR.glob("*.md"))
    if not spec_files:
        raise FileNotFoundError(f"No .md files found in {SPECS_DIR}")

    print(f"Found {len(spec_files)} spec files:")
    for f in spec_files:
        print(f"  {f.name}")

    # Build chunks from all files
    all_chunks: list[dict] = []
    for spec_file in spec_files:
        text = spec_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, source=spec_file.stem)
        print(f"  {spec_file.name} → {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\nTotal chunks to ingest: {len(all_chunks)}")

    # Init ChromaDB persistent client
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Embedding function — sentence-transformers, runs locally
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    # Drop and recreate collection for clean ingest
    existing = [c.name for c in client.list_collections()]
    if COLLECTION in existing:
        client.delete_collection(COLLECTION)
        print(f"Dropped existing collection: {COLLECTION}")

    collection = client.create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Add chunks in batches
    BATCH = 50
    for start in range(0, len(all_chunks), BATCH):
        batch = all_chunks[start : start + BATCH]
        collection.add(
            ids        = [c["chunk_id"] for c in batch],
            documents  = [c["text"]     for c in batch],
            metadatas  = [
                {"source": c["source"], "heading": c["heading"]}
                for c in batch
            ],
        )

    print(f"\nIngestion complete.")
    print(f"Collection : {COLLECTION}")
    print(f"Documents  : {collection.count()}")
    print(f"Persisted  : {CHROMA_DIR}")


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

def smoke_test(query: str = "how to correct ROUTING_MISMATCH") -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    collection = client.get_collection(name=COLLECTION, embedding_function=ef)

    results = collection.query(query_texts=[query], n_results=3)

    print(f"\nSmoke test query: '{query}'")
    print("-" * 60)
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        print(f"\nResult {i+1} | source={meta['source']} | heading={meta['heading']} | distance={dist:.4f}")
        print(doc[:300])
        print("...")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ingest()
    smoke_test()