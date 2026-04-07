from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from src.state import AgentState, AppliedFix, RagChunk

# ---------------------------------------------------------------------------
# ChromaDB config — must match ingest_specs.py
# ---------------------------------------------------------------------------

CHROMA_DIR  = Path(__file__).parent.parent.parent / "data" / "chroma_db"
COLLECTION  = "iata_specs"
EMBED_MODEL = "all-MiniLM-L6-v2"

# Retrieve top-3 chunks per issue
N_RESULTS = 3

# Similarity threshold — distances above this mean retrieval is not useful
MAX_DISTANCE = 0.60

# Confidence threshold — apply a RAG fix only if distance is this close
HIGH_CONFIDENCE_DISTANCE = 0.45

# ---------------------------------------------------------------------------
# Lazy client — initialised once per process
# ---------------------------------------------------------------------------

_client: chromadb.PersistentClient | None = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        _collection = _client.get_collection(
            name=COLLECTION,
            embedding_function=ef,
        )
    return _collection


# ---------------------------------------------------------------------------
# Query builder — turns an issue into a retrieval query
# ---------------------------------------------------------------------------

def _build_query(issue: dict) -> str:
    code  = issue["issue_code"]
    field = issue["field"]
    raw   = issue["raw_value"]
    return f"how to correct {code} error in {field} field with value {raw}"


# ---------------------------------------------------------------------------
# RAG fix attempt — deterministic corrections from spec
# Only applied when retrieved chunk is very close (distance < HIGH_CONFIDENCE_DISTANCE)
# and the fix can be derived without LLM reasoning.
# ---------------------------------------------------------------------------

def _attempt_rag_fix(
    issue: dict,
    chunks: list[RagChunk],
) -> AppliedFix | None:
    """
    Attempt a fix using retrieved spec context.
    Currently handles:
      - INVALID_AIRPORT_FORMAT (lowercase) — spec confirms uppercase rule
      - UNKNOWN_AWB_PREFIX — spec confirms prefix is unknown, no fix applied
    Returns an AppliedFix or None.
    """
    code      = issue["issue_code"]
    field     = issue["field"]
    raw_value = issue["raw_value"]

    # Only attempt if best chunk is close enough
    if not chunks or chunks[0]["distance"] > HIGH_CONFIDENCE_DISTANCE:
        return None

    # INVALID_AIRPORT_FORMAT — if raw is lowercase letters only → uppercase
    if code == "INVALID_AIRPORT_FORMAT":
        if raw_value.isalpha() and raw_value == raw_value.lower() and len(raw_value) == 3:
            corrected = raw_value.upper()
            return AppliedFix(
                node="rag_retriever",
                field=field,
                old_value=raw_value,
                new_value=corrected,
                confidence=0.88,
                rationale=f"RAG: Spec confirms IATA codes must be 3 uppercase letters. '{raw_value}' → '{corrected}'.",
            )

    return None


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def rag_retriever_node(state: AgentState) -> dict:
    """
    For each unresolved issue, query ChromaDB for relevant spec chunks.
    Stores all retrieved chunks in state['rag_context'].
    Applies high-confidence fixes directly where possible.
    Leaves the rest for llm_corrector_node.
    """
    # Get unresolved issues — prefer validation_result if available
    validation = state.get("validation_result")
    if validation and validation.get("remaining_issues"):
        issues = validation["remaining_issues"]
    else:
        issues = state.get("issues", [])

    if not issues:
        return {"rag_context": [], "escalation_tier": 1}

    collection     = _get_collection()
    rag_context    : list[RagChunk] = []
    new_fixes      : list[AppliedFix] = list(state.get("fixes_applied", []))
    resolved_codes : set[str] = set()

    for issue in issues:
        query   = _build_query(issue)
        code    = issue["issue_code"]

        results = collection.query(
            query_texts=[query],
            n_results=N_RESULTS,
        )

        docs      = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        # Collect useful chunks (within distance threshold)
        issue_chunks: list[RagChunk] = []
        for doc, meta, dist in zip(docs, metadatas, distances):
            if dist <= MAX_DISTANCE:
                issue_chunks.append(RagChunk(
                    issue_code=code,
                    heading=meta.get("heading", ""),
                    source=meta.get("source", ""),
                    text=doc,
                    distance=dist,
                ))

        rag_context.extend(issue_chunks)

        # Attempt a direct fix from spec
        fix = _attempt_rag_fix(issue, issue_chunks)
        if fix:
            new_fixes.append(fix)
            resolved_codes.add(code)

    return {
        "rag_context":    rag_context,
        "fixes_applied":  new_fixes,
        "escalation_tier": 1,
    }