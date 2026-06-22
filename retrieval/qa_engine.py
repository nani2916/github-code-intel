"""
Q&A Engine — answers questions about a codebase using RAG + Claude.

Supports both regular and streaming responses.
"""
from __future__ import annotations
import anthropic
from ingestion.vector_store import search_chunks, get_repo_stats
from config.settings import get_settings


QA_SYSTEM = """You are an expert code assistant helping developers understand a specific codebase.

You will be given:
1. A question about the codebase
2. Relevant code chunks retrieved from the repo

Rules:
- Answer ONLY based on the provided code. Do not guess or make things up.
- If the answer isn't in the provided chunks, say so clearly and suggest what to look for.
- Be specific: mention exact file names, function names, line patterns.
- Format code references as `filename.py` and inline code as `function_name()`.
- Keep answers focused and practical — developers want to act, not read essays.
- If the question is about how something works, trace the actual code flow.
- Use Markdown formatting for readability."""


def _build_context(repo: str, question: str, chunks: list[dict]) -> str:
    context_parts = [
        f"Repository: {repo}",
        f"Question: {question}\n",
        "--- RELEVANT CODE ---",
    ]
    for i, chunk in enumerate(chunks):
        context_parts.append(
            f"\n[{i+1}] {chunk['path']} (relevance: {chunk['score']})\n"
            f"```{chunk['language']}\n{chunk['text'][:1000]}\n```"
        )
    return "\n".join(context_parts)


async def answer_question(repo: str, question: str) -> dict:
    """Regular (non-streaming) answer."""
    s = get_settings()
    stats = get_repo_stats(repo)

    if stats["chunks"] == 0:
        return {
            "answer": f"I haven't indexed `{repo}` yet. Use the **Ingest Repo** button first.",
            "sources": [],
            "chunks_used": 0,
            "indexed": False,
        }

    chunks = search_chunks(repo=repo, query=question, k=6)

    if not chunks:
        return {
            "answer": "I couldn't find relevant code for your question. Try rephrasing or checking the repo is indexed.",
            "sources": [],
            "chunks_used": 0,
            "indexed": True,
        }

    context = _build_context(repo, question, chunks)
    client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)

    message = await client.messages.create(
        model=s.claude_model,
        max_tokens=1500,
        system=QA_SYSTEM,
        messages=[{"role": "user", "content": context}],
    )

    return {
        "answer": message.content[0].text,
        "sources": [{"path": c["path"], "score": c["score"]} for c in chunks],
        "chunks_used": len(chunks),
        "indexed": True,
    }


async def answer_question_stream(repo: str, question: str):
    """
    Streaming answer — yields text as it arrives from Claude word by word.
    Used by the /ask/stream SSE endpoint.

    Yields:
      data: <text>           — piece of the answer
      data: [SOURCES] {...}  — sources JSON at the end
      data: [DONE]           — end of stream
    """
    import json
    s = get_settings()
    stats = get_repo_stats(repo)

    if stats["chunks"] == 0:
        yield f"data: I haven't indexed `{repo}` yet. Use the Ingest Repo button first.\n\n"
        yield "data: [DONE]\n\n"
        return

    chunks = search_chunks(repo=repo, query=question, k=6)

    if not chunks:
        yield "data: I couldn't find relevant code for your question. Try rephrasing or checking the repo is indexed.\n\n"
        yield "data: [DONE]\n\n"
        return

    context = _build_context(repo, question, chunks)
    client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)

    async with client.messages.stream(
        model=s.claude_model,
        max_tokens=1500,
        system=QA_SYSTEM,
        messages=[{"role": "user", "content": context}],
    ) as stream:
        async for text in stream.text_stream:
            escaped = text.replace("\n", "\\n")
            yield f"data: {escaped}\n\n"

    sources = [{"path": c["path"], "score": c["score"]} for c in chunks]
    yield f"data: [SOURCES] {json.dumps(sources)}\n\n"
    yield "data: [DONE]\n\n"