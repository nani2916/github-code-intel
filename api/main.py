"""
FastAPI app — the backbone connecting everything.

Routes:
  POST /webhook/github        GitHub webhook (push, PR events)
  POST /ingest                Manually ingest a repo by URL
  POST /ask                   Ask a question about a repo
  GET  /summary/{owner}/{repo} Get auto-generated summary
  GET  /stats/{owner}/{repo}   Index stats for a repo
  GET  /repos                  List all indexed repos
  GET  /                       Serve the web UI
"""
import hashlib
import hmac
import json
import logging

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import get_settings
from ingestion.ingestor import ingest_repo
from ingestion.vector_store import get_repo_stats, list_indexed_repos
from retrieval.summariser import generate_summary, generate_pr_comment
from retrieval.qa_engine import answer_question, answer_question_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub Code Intelligence", version="1.0.0")


# ── Request models ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    repo: str       # "owner/repo"
    ref: str = "HEAD"

class AskRequest(BaseModel):
    repo: str       # "owner/repo"
    question: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("ui/index.html") as f:
        return f.read()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Manually trigger ingestion of a GitHub repo.
    Runs in background — returns immediately.
    """
    # Validate format
    if "/" not in req.repo or len(req.repo.split("/")) != 2:
        raise HTTPException(400, "repo must be in format 'owner/repo'")

    background_tasks.add_task(ingest_repo, req.repo, req.ref)
    return {"status": "ingestion_started", "repo": req.repo}


@app.post("/ask")
async def ask(req: AskRequest):
    """Answer a question about a repo using RAG + Claude."""
    if not req.question.strip():
        raise HTTPException(400, "question cannot be empty")

    result = await answer_question(repo=req.repo, question=req.question)
    return result


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """Streaming version of /ask — returns words as they arrive from Claude."""
    if not req.question.strip():
        raise HTTPException(400, "question cannot be empty")
    return StreamingResponse(
        answer_question_stream(repo=req.repo, question=req.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/summary/{owner}/{repo_name}")
async def summary(owner: str, repo_name: str):
    """Get or generate a summary for a repo."""
    repo = f"{owner}/{repo_name}"
    text = await generate_summary(repo=repo)
    return {"repo": repo, "summary": text}


@app.get("/stats/{owner}/{repo_name}")
async def stats(owner: str, repo_name: str):
    repo = f"{owner}/{repo_name}"
    return {"repo": repo, **get_repo_stats(repo)}


@app.get("/repos")
async def repos():
    return {"repos": list_indexed_repos()}


@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives GitHub webhook events.
    On push: re-ingests the repo and posts a PR comment with the summary.
    """
    s = get_settings()
    body = await request.body()

    # Verify webhook signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        s.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    if event == "push":
        repo = payload["repository"]["full_name"]
        ref = payload.get("ref", "HEAD").replace("refs/heads/", "")
        logger.info(f"Push event: {repo}@{ref}")
        background_tasks.add_task(_handle_push, repo, ref)

    elif event == "pull_request" and payload.get("action") == "opened":
        repo = payload["repository"]["full_name"]
        pr_number = payload["pull_request"]["number"]
        pr_title = payload["pull_request"]["title"]
        changed_files = [f["filename"] for f in payload.get("files", [])]
        background_tasks.add_task(_handle_pr, repo, pr_number, pr_title, changed_files)

    return {"status": "received"}


async def _handle_push(repo: str, ref: str):
    """Re-ingest on push."""
    try:
        result = await ingest_repo(repo=repo, ref=ref)
        logger.info(f"Push ingestion complete: {result}")
    except Exception as e:
        logger.error(f"Push ingestion failed for {repo}: {e}")


async def _handle_pr(repo: str, pr_number: int, pr_title: str, changed_files: list[str]):
    """Post summary comment on new PR."""
    from tools.github import GitHubClient
    try:
        comment = await generate_pr_comment(
            repo=repo, pr_title=pr_title, changed_files=changed_files
        )
        gh = GitHubClient()
        url = await gh.post_issue_comment(repo=repo, issue_number=pr_number, body=comment)
        logger.info(f"Posted PR comment: {url}")
    except Exception as e:
        logger.error(f"PR comment failed for {repo}#{pr_number}: {e}")