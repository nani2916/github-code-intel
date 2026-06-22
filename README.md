# GitHub Code Intelligence

Ask questions about any GitHub repo in plain English. Get instant answers backed by the actual code.

## What it does

**Auto-summary** — point it at any repo, it reads all the code and writes a plain-English explanation: what it does, how it works, key files, tech stack.

**Chat with code** — ask anything: "where is the payment logic?", "how does auth work?", "what does this function do?" — it searches the real code and Claude answers with specific file references.

**GitHub bot** — add a webhook and it automatically posts a summary comment on every new PR.

---

## Setup (15 minutes)

### Step 1 — Get your API keys

**Anthropic API key** (free $5 credits, no card needed for basic use):
1. Go to https://console.anthropic.com
2. Sign up / log in
3. Click "API Keys" → "Create Key"
4. Copy the key (starts with `sk-ant-`)

**GitHub token** (completely free):
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name like "code-intelligence"
4. Check these boxes: `repo` (full), `read:org`
5. Click "Generate token"
6. Copy the token (starts with `ghp_`)

---

### Step 2 — Configure the app

```bash
# In the project folder:
cp .env.example .env
```

Open `.env` and fill in your keys:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
GITHUB_TOKEN=ghp_your-token-here
GITHUB_WEBHOOK_SECRET=any-random-string-you-make-up
```

---

### Step 3 — Install and run

You need Python 3.11+ installed. Then:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn api.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser. That's it.

---

## Using it

### Chat with any public repo

1. Open http://localhost:8000
2. Type a repo name in the sidebar: e.g. `tiangolo/fastapi`
3. Click **Ingest repo** — wait ~30 seconds
4. Click **Check index stats** to confirm it's ready
5. Ask anything in the chat!

### Generate a summary

1. Ingest the repo (same as above)
2. Click the **Auto summary** tab
3. Click **Generate summary**

### Try these repos (all public, no token needed)

- `tiangolo/fastapi` — medium size, Python
- `axios/axios` — JavaScript HTTP client
- `pallets/flask` — classic Python web framework
- `expressjs/express` — Node.js web framework

---

## GitHub webhook (optional)

To get automatic PR comments whenever code is pushed:

1. In your GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://your-server.com/webhook/github`
3. Content type: `application/json`
4. Secret: the `GITHUB_WEBHOOK_SECRET` from your `.env`
5. Events: check "Pushes" and "Pull requests"

For local testing, use [ngrok](https://ngrok.com) to expose your local server:
```bash
ngrok http 8000
# Use the https URL ngrok gives you as your webhook URL
```

---

## Project structure

```
github-code-intel/
├── api/
│   └── main.py           # FastAPI routes
├── ingestion/
│   ├── ingestor.py       # Fetch → chunk → store pipeline
│   ├── chunker.py        # Splits code into RAG chunks
│   └── vector_store.py   # ChromaDB wrapper
├── retrieval/
│   ├── qa_engine.py      # RAG + Claude Q&A
│   └── summariser.py     # Full repo summary generation
├── tools/
│   └── github.py         # GitHub API client
├── config/
│   └── settings.py       # Config from .env
├── ui/
│   └── index.html        # Web interface (no framework)
├── .env.example
├── requirements.txt
└── README.md
```

## Cost

- GitHub API: **free**
- ChromaDB: **free** (runs locally)
- Anthropic API: **$5 free credits** on signup = hundreds of Q&A sessions

For a typical session (ingest 1 repo + 20 questions): ~$0.10
