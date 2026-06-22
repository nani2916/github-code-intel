"""
Code Chunker — splits source files into overlapping chunks for RAG.

Strategy:
- Small files (< 60 lines): one chunk = whole file
- Large files: chunk by function/class boundaries when possible,
  otherwise sliding window with overlap
- Each chunk keeps its file path + language as metadata
"""
from __future__ import annotations
import re


MAX_CHUNK_LINES = 60
OVERLAP_LINES = 10


def chunk_files(files: list[dict]) -> list[dict]:
    """
    Input:  list of {"path", "content", "language", "size"}
    Output: list of {"text", "path", "language", "chunk_index", "chunk_id"}
    """
    chunks = []
    for file in files:
        file_chunks = _chunk_file(file)
        chunks.extend(file_chunks)
    return chunks


def _chunk_file(file: dict) -> list[dict]:
    path = file["path"]
    content = file["content"]
    language = file["language"]
    lines = content.splitlines()

    if not lines:
        return []

    # Small file — one chunk
    if len(lines) <= MAX_CHUNK_LINES:
        return [_make_chunk(path, language, lines, 0)]

    # Try to split on function/class boundaries for code files
    if language in ("python", "javascript", "typescript", "go", "rust", "java", "csharp"):
        boundary_chunks = _split_on_boundaries(path, language, lines)
        if boundary_chunks:
            return boundary_chunks

    # Fallback: sliding window
    return _sliding_window(path, language, lines)


def _split_on_boundaries(path: str, language: str, lines: list[str]) -> list[dict]:
    """Split on function/class definition lines."""
    if language == "python":
        pattern = re.compile(r"^(def |class |async def )")
    elif language in ("javascript", "typescript"):
        pattern = re.compile(r"^(function |class |const \w+ = |export )")
    elif language == "go":
        pattern = re.compile(r"^func ")
    elif language in ("java", "csharp"):
        pattern = re.compile(r"^\s*(public|private|protected|static|void|class )")
    elif language == "rust":
        pattern = re.compile(r"^(pub |fn |struct |impl |enum )")
    else:
        return []

    boundaries = [0]
    for i, line in enumerate(lines):
        if i > 0 and pattern.match(line):
            boundaries.append(i)
    boundaries.append(len(lines))

    chunks = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = min(boundaries[idx + 1], start + MAX_CHUNK_LINES)
        chunk_lines = lines[start:end]
        if chunk_lines:
            chunks.append(_make_chunk(path, language, chunk_lines, idx, start_line=start))

    return chunks if len(chunks) > 1 else []


def _sliding_window(path: str, language: str, lines: list[str]) -> list[dict]:
    chunks = []
    idx = 0
    start = 0
    while start < len(lines):
        end = min(start + MAX_CHUNK_LINES, len(lines))
        chunks.append(_make_chunk(path, language, lines[start:end], idx, start_line=start))
        idx += 1
        start += MAX_CHUNK_LINES - OVERLAP_LINES
    return chunks


def _make_chunk(
    path: str,
    language: str,
    lines: list[str],
    chunk_index: int,
    start_line: int = 0,
) -> dict:
    text = f"File: {path}\n\n" + "\n".join(lines)
    return {
        "text": text,
        "path": path,
        "language": language,
        "chunk_index": chunk_index,
        "start_line": start_line,
        "chunk_id": f"{path}::{chunk_index}",
    }
