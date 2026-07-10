"""
Suggestions engine — analyses a repo's tech stack and returns:
  - Related research papers
  - Similar open source projects with different approaches
  - YouTube videos to learn more
  - Ideas to improve or extend the project
"""
from __future__ import annotations
import json
import anthropic
from config.settings import get_settings
from ingestion.vector_store import get_repo_stats, search_chunks


SUGGESTIONS_SYSTEM = """You are a senior AI/ML engineer and technical advisor.

Given a GitHub repository's tech stack and code summary, provide helpful suggestions.
Your response must be ONLY a valid JSON object with this exact structure, no other text:

{
  "tech_stack": ["Python", "FastAPI", "React"],
  "papers": [
    {
      "title": "Attention Is All You Need",
      "authors": "Vaswani et al., 2017",
      "summary": "Introduced the Transformer architecture that powers most modern LLMs",
      "url": "https://arxiv.org/abs/1706.03762",
      "relevance": "Directly relevant if using transformer-based models"
    }
  ],
  "similar_projects": [
    {
      "name": "LlamaIndex",
      "description": "Data framework for LLM applications with different RAG approach",
      "url": "https://github.com/jerryjliu/llama_index",
      "difference": "Uses hierarchical node parsing vs flat chunking"
    }
  ],
  "videos": [
    {
      "title": "RAG from Scratch - Full Course",
      "channel": "LangChain",
      "url": "https://www.youtube.com/watch?v=sVcwVQRHIc8",
      "why_watch": "Covers advanced retrieval techniques directly applicable to this project"
    }
  ],
  "improvement_ideas": [
    {
      "title": "Add authentication middleware",
      "description": "Implement JWT-based auth to secure the API endpoints and protect user data.",
      "difficulty": "Medium",
      "impact": "High"
    }
  ]
}

Rules:
- Only suggest things DIRECTLY relevant to the detected tech stack
- Papers must be real, well-known papers
- Projects must be real GitHub repos
- YouTube videos must be real videos from reputable channels
- improvement_ideas should be specific and actionable
- difficulty: "Easy" | "Medium" | "Hard"
- impact: "Low" | "Medium" | "High"
- Return 3-4 items in each category
- Return ONLY the JSON object, no markdown, no explanation
"""


async def generate_suggestions(repo: str) -> dict:
    s = get_settings()
    stats = get_repo_stats(repo)

    if stats["chunks"] == 0:
        return {
            "error": f"Repo `{repo}` not indexed yet. Ingest it first.",
            "tech_stack": [],
            "papers": [],
            "similar_projects": [],
            "videos": [],
            "improvement_ideas": [],
        }

    # Pull representative chunks to understand the tech stack
    queries = [
        "import library framework dependencies",
        "main architecture design pattern",
        "database storage models",
        "API routes endpoints",
    ]

    seen = set()
    chunks = []
    for q in queries:
        results = search_chunks(repo=repo, query=q, k=3)
        for r in results:
            if r["path"] not in seen:
                seen.add(r["path"])
                chunks.append(r)
        if len(chunks) >= 10:
            break

    context = f"""Repository: {repo}
Languages detected: {', '.join(stats.get('languages', []))}
Files indexed: {stats.get('files', 0)}

--- CODE SAMPLES ---
"""
    for chunk in chunks[:8]:
        context += f"\n### {chunk['path']}\n```{chunk['language']}\n{chunk['text'][:500]}\n```\n"

    client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)

    message = await client.messages.create(
        model=s.claude_model,
        max_tokens=3000,
        system=SUGGESTIONS_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Analyse this repository and provide suggestions as JSON:\n\n{context}"
        }],
    )

    raw = message.content[0].text.strip()

    # Clean markdown fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            if part.startswith("json"):
                raw = part[4:].strip()
                break
            elif part.strip().startswith("{"):
                raw = part.strip()
                break

    # Find JSON object
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "tech_stack": stats.get("languages", []),
            "papers": [],
            "similar_projects": [],
            "videos": [],
            "improvement_ideas": [],
            "error": "Could not parse suggestions. Try again.",
        }