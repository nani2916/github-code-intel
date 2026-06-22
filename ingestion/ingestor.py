"""
Ingestor — ties together GitHub fetch → chunk → store.
Called on webhook push events and manual /ingest API calls.
"""
from __future__ import annotations
from tools.github import GitHubClient
from ingestion.chunker import chunk_files
from ingestion.vector_store import store_chunks, get_repo_stats


async def ingest_repo(repo: str, ref: str = "HEAD") -> dict:
    """
    Full ingestion pipeline for a repo.
    Returns summary of what was indexed.
    """
    github = GitHubClient()

    # 1. Fetch all code files from GitHub
    print(f"[ingest] Fetching files from {repo}@{ref}...")
    files = await github.get_repo_files(repo=repo, ref=ref)
    print(f"[ingest] Got {len(files)} files")

    if not files:
        return {"repo": repo, "files": 0, "chunks": 0, "error": "No files found"}

    # 2. Chunk into RAG-ready pieces
    chunks = chunk_files(files)
    print(f"[ingest] Created {len(chunks)} chunks")

    # 3. Store in Chroma
    stored = store_chunks(repo=repo, chunks=chunks)
    print(f"[ingest] Stored {stored} chunks in vector DB")

    stats = get_repo_stats(repo)
    return {
        "repo": repo,
        "ref": ref,
        "files_fetched": len(files),
        "chunks_stored": stored,
        "languages": stats.get("languages", []),
    }
