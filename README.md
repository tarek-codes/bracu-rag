# BRAC University Information Chatbot (RAG)

An AI-powered, retrieval-augmented generation (RAG) assistant for BRAC University. The chatbot answers questions about admissions, tuition and fees, academic policies, degree curricula, and student services strictly using a curated institutional knowledge base.

---

## Overview

The **BRAC University Information Chatbot** provides accurate, context-aware information to prospective students, current students, faculty, and visitors. The system is engineered around strict grounding: it answers exclusively using verified university documentation, cites specific sources for every answer, and gracefully declines or clarifies out-of-scope questions instead of hallucinating outside facts.

### Core Capabilities

- **Strict Knowledge Grounding**: Answers are synthesized solely from retrieved knowledge base context. If retrieved passages do not meet relevance thresholds, the system provides a polite fallback response.
- **Source Citations**: Every generated answer includes clickable citations to the exact source document, page, and excerpt.
- **Intent Routing**: Before any retrieval, each message is classified. Greetings, thanks, gibberish, prompt injection, requests for private data, harmful requests, out-of-domain questions (general knowledge, coding, arithmetic, other universities) and ambiguous questions get a fixed, polite reply without touching the knowledge base or the answering model.
- **Document Targeting**: The router sees a catalog of indexed documents and picks the 1 to 3 most likely to hold the answer, so search starts in the right place. If the targeted search finds nothing it widens automatically.
- **Intelligent Hybrid Retrieval**: Combines a FAISS semantic dense index over stored embeddings and PostgreSQL full-text keyword search using Reciprocal Rank Fusion (RRF).
- **Question-Aware Answers**: Calculations, comparisons, personal situations, recommendations, future-dated and claim-verification questions get tailored guidance so the model shows its working, avoids speculation and never presents advice as official policy.
- **Multi-Provider LLM with Fallbacks**: Answers stream from OpenRouter (primary model plus an ordered list of low-cost fallbacks), then Groq. The chat shows which model and provider answered.
- **Postgres and Chroma Cloud**: Every chunk and vector is stored in PostgreSQL (source of truth) and mirrored to Chroma Cloud for cloud access.
- **Two-Stage Reranking**: Re-scores top retrieved candidates using a locally hosted cross-encoder reranker before passing context to the generator.
- **Context-Aware Conversational Memory**: Tracks multi-turn dialogue within a session, rewriting follow-up queries into standalone search questions.
- **Multi-Format Ingestion**: Ingests markdown, PDFs, plain text, DOCX, and web pages with structure-aware chunking. A whole logical unit (a course, a faculty member) stays in one chunk of up to 4000 characters, so facts are never stored apart from the name they describe.
- **Deterministic Incremental Updates**: Uses file-level and chunk-level SHA-256 hashes to prevent redundant parsing and re-embedding when refreshing knowledge documents.
- **Role-Based Access Control**: Secure JWT authentication (httpOnly cookies, Argon2 hashing) with separate permissions for users and administrators.
- **Interactive Documentation**: Auto-generated interactive OpenAPI documentation via FastAPI Swagger UI and ReDoc.

---

## Architecture

The system maintains a clean decoupling between the frontend presentation layer and the backend service layer:

```
Next.js 16.3.7 (UI Only)  <-- HTTPS/JSON + SSE -->  FastAPI 0.142.2 (Backend Logic)
                                                    |
                         +--------------------------+--------------------------+
                         |                                                     |
                  PostgreSQL + pgvector                            OpenRouter (primary LLM + fallbacks)
                  (Auth, chats, documents,                         Groq (last fallback)
                   chunks, embeddings, jobs)                       Local models (Embedding, Reranker)
                         |
                  Chroma Cloud (mirror of chunks and vectors)
```

### Retrieval & Answer Pipeline

1. **User Message & Session**: Query received alongside session ID.
2. **Intent Routing**: Rules handle greetings, thanks, gibberish, injection, private data, harmful and pure-math requests. One small LLM call classifies the rest (knowledge question, out of domain, ambiguous), rewrites follow-ups into a standalone query and picks the target documents.
3. **Dense & Sparse Search**: Generates a query vector via the local embedding service, searches a FAISS inner-product index over normalized stored vectors alongside Postgres full-text search within the targeted documents, and merges candidates via Reciprocal Rank Fusion.
4. **Cross-Encoder Reranking**: Locally reranks candidate chunks down to the top most relevant passages.
5. **Threshold Validation**: If top candidate relevance score falls below the cutoff, generation stops immediately with a standardized "not found in knowledge base" fallback.
6. **Grounding & Generation**: Delivers retrieved passages into a strictly bounded system prompt, with guidance matched to the question type, and streams the answer via Server-Sent Events (SSE). Providers are tried in order until one succeeds.
7. **Citation & Persistence**: Appends document titles, relative paths, and snippets, then persists messages and citations to PostgreSQL.

---

## Tech Stack

| Layer | Component | Version / Specification |
|---|---|---|
| **Backend Framework** | FastAPI | 0.142.2 (Python 3.12, async, Pydantic v2) |
| **Database & Vector Store** | PostgreSQL + pgvector + FAISS + Chroma Cloud | PostgreSQL stores metadata and vectors; FAISS provides local normalized-vector search; Chroma Cloud holds a synced copy of every chunk and vector |
| **Frontend Framework** | Next.js | 16.3.7 (TypeScript strict, App Router, `proxy.ts`) |
| **Frontend UI & Styling** | Tailwind CSS & shadcn/ui | Tailwind v4, Lucide icons, TanStack Query |
| **Runtime & Package Managers** | Bun & uv | Bun 1.4.2 (frontend), uv (backend) |
| **LLM Provider** | OpenRouter, then Groq | Primary model plus ordered low-cost fallbacks (`OPENROUTER_FALLBACK_MODELS`), small non-reasoning model for routing |
| **Embedding Model** | sentence-transformers/all-MiniLM-L6-v2 | Local SentenceTransformers model, 384 dimensions |
| **Reranker Model** | cross-encoder/ms-marco-MiniLM-L-6-v2 | Lightweight local cross-encoder reranker |
| **Document Processing** | PyMuPDF4LLM & Trafilatura | PDF markdown conversion, web scraping extraction |
| **Security & Auth** | Argon2 & JWT | `argon2-cffi`, secure httpOnly cookie session tokens |
| **Observability** | Structlog | JSON structured logging with `X-Request-ID` tracing |

---

## Repository Structure

```text
bracu_RAG/
├── backend/                  # FastAPI backend application
│   ├── app/
│   │   ├── api/v1/          # Route handlers (auth, chat, documents, users)
│   │   ├── core/            # Configuration, security, logging
│   │   ├── db/              # Database session and base models
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Chat (router, prompts, streaming), ingestion, retrieval, vectorstore (Chroma), auth
│   │   └── tasks/           # Background tasks for document processing
│   ├── alembic/             # Database migration scripts
│   └── tests/               # Unit, integration, and eval test suites
├── frontend/                 # Next.js frontend application
│   ├── app/                 # App Router pages (chat, auth, admin)
│   ├── components/          # Reusable UI components (shadcn/ui)
│   └── lib/                 # API client and generated OpenAPI types
├── output/                   # Processed knowledge base and scraped data
│   ├── pages/               # Scraped cleaned Markdown documents
│   ├── pdfs/                # Scraped official university PDFs
│   └── kb_documents.jsonl   # Consolidated RAG document dataset
├── scraper/                  # Playwright browser crawler (Phase 1)
├── CLAUDE.md                 # Engineering guidelines and instructions
├── techstack.md              # Detailed architecture and technology choices
└── README.md                 # Project documentation
```

---

## Setup and Development

### Prerequisites

- **Python**: 3.12+ (managed with `uv`)
- **Node/Frontend Runtime**: Bun 1.4.2+
- **Database**: PostgreSQL 17/18 with `pgvector` extension. On Windows, run via Docker Desktop (`docker compose up -d`) or local service.

### Quick Start (Windows)

A single PowerShell script starts all services (PostgreSQL via Docker, FastAPI backend, and Next.js frontend):

```powershell
.\run_project.ps1
```

Or step by step:

1. **Start PostgreSQL with pgvector**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup_postgres.ps1
   # Or using Docker Compose directly:
   docker compose up -d
   ```

2. **Backend**:
   ```powershell
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python -m app.cli ingest-folder
   uv run uvicorn app.main:app --reload
   ```

3. **Frontend**:
   ```powershell
   cd frontend
   bun install
   bun run dev
   ```

### Backend Setup (Linux / macOS)

```bash
cd backend

# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Bulk ingest knowledge base documents
uv run python -m app.cli ingest-folder

# Start the API server
uv run uvicorn app.main:app --reload
```

API documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

The API uses access and refresh tokens in `httpOnly` cookies. The frontend sends
these cookies with `credentials: include`; do not copy tokens into local storage.
For local development, set `CORS_ORIGINS=http://localhost:3000` in the backend
environment and start both services.

### Frontend Setup (Linux / macOS)

```bash
cd frontend

# Install dependencies
bun install

# Start the development server
bun run dev
```

The chat application will be accessible at `http://localhost:3000`.

### Configuration

Copy `backend/.env.example` to `backend/.env` and fill in real values. Keep real keys out of any public repository.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `JWT_SECRET` | Signing secret for access and refresh tokens |
| `CORS_ORIGINS` | Allowed frontend origins, for example `http://localhost:3000` |
| `OPENROUTER_API_KEY` | OpenRouter key (primary provider) |
| `OPENROUTER_MODEL` | Primary answering model |
| `OPENROUTER_FALLBACK_MODELS` | Comma separated models tried in order if the primary fails |
| `OPENROUTER_REWRITE_MODEL` | Small non-reasoning model used for intent routing and query rewrite |
| `GROQ_API_KEY`, `GROQ_ANSWER_MODEL` | Groq, used after every OpenRouter model fails |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM` | Local embedding model and its dimension (384 for all-MiniLM-L6-v2) |
| `SIMILARITY_THRESHOLD` | Minimum relevance before the model is called |
| `KB_SOURCE_DIR` | Folder of `.md` and `.pdf` files for bulk ingest (`output` by default) |
| `CHROMA_API_KEY`, `CHROMA_HOST`, `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_COLLECTION_NAME` | Chroma Cloud mirror. Leave the key empty to disable |

### Ingesting knowledge

```bash
cd backend
uv run python -m app.cli ingest-folder              # incremental: unchanged files are skipped
uv run python -m app.cli ingest-folder --rechunk    # re-chunk unchanged files after a chunker change
uv run python -m app.cli sync-chroma                # mirror all chunks to Chroma Cloud
uv run python -m app.cli create-admin               # create an administrator
```

Ingestion is incremental. A file whose hash is unchanged is skipped, and for a changed file only new chunks are embedded while removed chunks are deleted. Running it twice in a row embeds nothing the second time. Each chunk written to PostgreSQL is also upserted to Chroma Cloud, and removed from it when the chunk or document is deleted. If Chroma is unreachable, ingestion continues and `sync-chroma` repairs the difference later.

### Tests and evaluation set

Tests run against their own `bracu_rag_test` database, which is created and migrated automatically, so they never touch the real knowledge base. Run the backend checks from `backend/`:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```

The checked-in RAG evaluation fixture is
[`backend/tests/eval/questions.json`](backend/tests/eval/questions.json). It
contains grounded questions tied to real files in `output/`, plus out-of-scope
questions that must produce the BRAC University knowledge-base fallback. Verify
its source-file contract with:

```bash
uv run pytest tests/test_evaluation_set.py
```

When changing chunking, retrieval, reranking, thresholds, or prompts, run the
full suite and review the evaluation questions against returned citations and
fallbacks. The fixture does not replace an end-to-end run against PostgreSQL,
the local embedding/reranker models, and the mocked Groq service used by tests.

### Verify registration and login

The backend auth flow is covered by
[`backend/tests/test_auth.py`](backend/tests/test_auth.py), including:

- account creation and duplicate-email rejection;
- password authentication and invalid-password rejection;
- secure access and refresh cookies;
- `/api/v1/auth/me`;
- refresh-token rotation and logout.

To exercise the same flow manually with the running API:

```bash
curl -i -c /tmp/bracu-cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"Password123!","full_name":"Test Student"}' \
  http://localhost:8000/api/v1/auth/register

curl -i -b /tmp/bracu-cookies.txt -c /tmp/bracu-cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"Password123!"}' \
  http://localhost:8000/api/v1/auth/login

curl -i -b /tmp/bracu-cookies.txt http://localhost:8000/api/v1/auth/me
```

The web pages are available at `/register` and `/login`. Registration creates
a standard user, then signs the user in and redirects to `/chat`; login
redirects standard users to `/chat` and admins to `/admin/knowledge`.

---

## Scraping Phase (Completed)

The initial knowledge base was assembled using a custom, high-fidelity browser crawler built with **Playwright (Chromium)**.

### Target Scope

The crawler targeted public university information across key domains:
- General university information and administration
- Undergraduate and graduate admissions
- Tuition, fee schedules, and payment policies
- Scholarships, waivers, and financial aid
- Academic degree programs and course curricula (e.g., CSE / CS departments)
- Academic policies, grading regulations, and residential semester guidelines
- Academic calendars, registration dates, and student services

### Interactive Content Capture

Rather than performing simple static HTTP requests, the crawler automated browser interactions to expand interactive UI elements while strictly prohibiting state-modifying actions:
- **Expanded controls**: Accordion/collapse sections, tabs, `aria-expanded=false` triggers, "Read more", "View details", "Show more", and content pagination.
- **Excluded actions**: Form submissions, login forms, admission applications, payments, and transactional buttons.
- **Focused Crawling**: Scored links against category keywords in `config.json` to filter out irrelevant press releases and event galleries.

### Scraper Execution & Artifacts

```bash
# Setup scraper environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Execute browser crawl
python run_scrape.py

# Build consolidated RAG JSONL corpus
python build_jsonl.py
```

Crawler artifacts generated under `output/`:
- `output/pages/`: Cleaned, structured Markdown extractions.
- `output/pdfs/`: Public institutional PDFs.
- `output/manifest.csv`: Comprehensive catalog of all processed web resources.
- `output/kb_documents.jsonl`: Formatted, consolidated document chunks for RAG ingestion.
- `output/state/`: Checkpoint records (`visited.jsonl`, `queue.json`) enabling pause/resume capability.
