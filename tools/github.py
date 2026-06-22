"""
GitHub API tool — fetches repo file trees, downloads code, posts comments.
Uses only the free GitHub REST API, no extra libraries needed.
"""
from __future__ import annotations
import base64
import httpx
from config.settings import get_settings


class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        s = get_settings()
        self.headers = {
            "Authorization": f"Bearer {s.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_repo_files(self, repo: str, ref: str = "HEAD") -> list[dict]:
        """
        Returns list of all text/code files in the repo.
        Each item: {"path": "src/main.py", "content": "...", "language": "python"}
        Skips binaries, images, lock files, node_modules etc.
        """
        SKIP_EXTENSIONS = {
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
            ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".gz",
            ".pdf", ".lock", ".bin", ".exe", ".so", ".dylib",
        }
        SKIP_DIRS = {
            "node_modules", ".git", "dist", "build", "__pycache__",
            ".next", "vendor", "venv", ".venv",
        }

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{self.BASE}/repos/{repo}/git/trees/{ref}?recursive=1",
                headers=self.headers,
            )
            if r.status_code == 404:
                raise ValueError(f"Repo '{repo}' not found or not accessible")
            r.raise_for_status()
            tree = r.json().get("tree", [])

        files = []
        for item in tree:
            if item["type"] != "blob":
                continue
            path: str = item["path"]

            # Skip unwanted dirs
            parts = path.split("/")
            if any(p in SKIP_DIRS for p in parts[:-1]):
                continue

            # Skip unwanted extensions
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            if ext in SKIP_EXTENSIONS:
                continue

            # Skip files > 100KB (too large to be useful)
            if item.get("size", 0) > 100_000:
                continue

            content = await self._fetch_file(repo, item["sha"])
            if content:
                files.append({
                    "path": path,
                    "content": content,
                    "language": _detect_language(path),
                    "size": item.get("size", 0),
                })

        return files

    async def _fetch_file(self, repo: str, sha: str) -> str | None:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.BASE}/repos/{repo}/git/blobs/{sha}",
                headers=self.headers,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            except Exception:
                return None

    async def post_issue_comment(self, repo: str, issue_number: int, body: str) -> str:
        """Post a comment on an issue or PR. Returns the comment URL."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.BASE}/repos/{repo}/issues/{issue_number}/comments",
                json={"body": body},
                headers=self.headers,
            )
            r.raise_for_status()
            return r.json()["html_url"]

    async def get_repo_info(self, repo: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.BASE}/repos/{repo}", headers=self.headers)
            r.raise_for_status()
            return r.json()


def _detect_language(path: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
        ".rs": "rust", ".java": "java", ".cs": "csharp", ".cpp": "cpp",
        ".c": "c", ".rb": "ruby", ".php": "php", ".swift": "swift",
        ".kt": "kotlin", ".md": "markdown", ".yaml": "yaml",
        ".yml": "yaml", ".json": "json", ".sh": "bash",
        ".dockerfile": "dockerfile", ".sql": "sql", ".html": "html",
        ".css": "css", ".tf": "terraform",
    }
    if path.lower().endswith("dockerfile"):
        return "dockerfile"
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext_map.get(ext, "text")
