"""
Vector Store — wraps ChromaDB for storing and searching code chunks.

Uses Chroma's built-in embedding function (no OpenAI needed).
Runs locally, stores data on disk at CHROMA_PATH.
"""
from __future__ import annotations
import chromadb
from chromadb.utils import embedding_functions
from config.settings import get_settings


def _get_client():
    s = get_settings()
    return chromadb.PersistentClient(path=s.chroma_path)


def _get_collection(repo: str):
    """Each repo gets its own collection. Name is sanitised for Chroma."""
    client = _get_client()
    safe_name = repo.replace("/", "__").replace("-", "_").lower()
    ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(
        name=f"repo_{safe_name}",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def store_chunks(repo: str, chunks: list[dict]) -> int:
    """
    Upsert all chunks for a repo. Clears old data first so re-ingestion
    always reflects the current state of the codebase.
    Returns number of chunks stored.
    """
    col = _get_collection(repo)

    # Clear existing data for this repo (full re-index on each push)
    existing = col.get()
    if existing["ids"]:
        col.delete(ids=existing["ids"])

    if not chunks:
        return 0

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "path": c["path"],
            "language": c["language"],
            "chunk_index": str(c["chunk_index"]),
            "start_line": str(c.get("start_line", 0)),
        }
        for c in chunks
    ]

    # Chroma has a batch limit — insert in batches of 100
    batch = 100
    for i in range(0, len(chunks), batch):
        col.upsert(
            ids=ids[i:i+batch],
            documents=documents[i:i+batch],
            metadatas=metadatas[i:i+batch],
        )

    return len(chunks)


def search_chunks(repo: str, query: str, k: int = 6) -> list[dict]:
    """
    Search for the k most relevant code chunks for a query.
    Returns list of {"text", "path", "language", "score"}
    """
    col = _get_collection(repo)
    count = col.count()
    if count == 0:
        return []

    results = col.query(
        query_texts=[query],
        n_results=min(k, count),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "path": meta.get("path", ""),
            "language": meta.get("language", ""),
            "score": round(1.0 - dist, 3),
        })

    return chunks


def get_repo_stats(repo: str) -> dict:
    """Return stats about what's indexed for a repo."""
    col = _get_collection(repo)
    count = col.count()
    if count == 0:
        return {"chunks": 0, "files": 0, "languages": []}

    all_items = col.get(include=["metadatas"])
    paths = {m["path"] for m in all_items["metadatas"]}
    langs = {m["language"] for m in all_items["metadatas"] if m.get("language")}

    return {
        "chunks": count,
        "files": len(paths),
        "languages": sorted(langs),
    }


def list_indexed_repos() -> list[str]:
    """Return all repos that have been indexed."""
    client = _get_client()
    cols = client.list_collections()
    repos = []
    for col in cols:
        if col.name.startswith("repo_"):
            name = col.name[5:].replace("__", "/").replace("_", "-")
            repos.append(name)
    return repos
