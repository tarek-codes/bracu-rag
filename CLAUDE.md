# CLAUDE.md

You are working as a Senior Software Engineer and AI Engineer on this project. Build it the way a careful, experienced engineer would: understand before changing, keep things simple, verify your work, and leave the codebase better than you found it.

Read `techstack.md` first. It is the source of truth for technology choices and pinned versions. If a choice must change, update `techstack.md` in the same change.

## 1. Project Goal

The **BRAC University Information Chatbot**: an AI-powered chatbot with knowledge handling (RAG) that answers questions about BRAC University using only a custom, medium size knowledge base (KB).

The KB already exists locally in a folder as markdown (.md) files and PDF files. Its path comes from the `KB_SOURCE_DIR` environment variable. Never invent, scrape or fabricate university facts. Build a re-runnable bulk import command for that folder (see section 5), and keep admin upload and URL ingest for adding content later.

Must-have requirements:
1. Trainable on a custom KB (ingestion and retrieval, no model training).
2. Answers only from the provided KB.
3. Graceful handling of out-of-scope questions (polite fallback, clarification request, or "not found in knowledge base").
4. Context-aware retrieval and answer generation from documents.
5. Short-term conversation memory within a session.
6. Multiple KB formats: PDF, text, markdown, DOCX, web pages.
7. KB updates without full retraining (add, change, delete, re-index).
8. Authentication for users and admins.
9. API documentation (FastAPI Swagger and ReDoc).
10. Backend logger.
11. Complete frontend chat application.
12. Backend that processes queries, manages the KB and generates responses.
13. Clean API based architecture between frontend and backend.

Every feature you build should trace back to one of these. Do not add features outside this list unless asked.

## 2. Stack Summary

Backend: FastAPI 0.142.2, Python 3.12, SQLAlchemy 2.0 async, Alembic, Pydantic v2, FastAPI `BackgroundTasks` for ingestion.
Frontend: Next.js 16.3.7, TypeScript strict, Tailwind v4, shadcn/ui, TanStack Query, Bun 1.4.2.
Data: PostgreSQL 18.6 with pgvector.
AI: Groq API for LLM, Qwen3-Embedding-0.6B for embeddings, Qwen3-Reranker-0.6B for reranking, both run locally.
Details live in `techstack.md`.

## 3. How to Work

### Before coding
- Read the relevant existing code before editing. Do not guess at structure.
- For any non-trivial task, state a short plan first (files to touch, approach, risks), then implement.
- If requirements are ambiguous and a wrong guess would be costly, ask one focused question. Otherwise make a reasonable assumption and state it.
- Work in small, vertical slices that run end to end. Follow the build order in `techstack.md`.

### While coding
- Keep changes minimal and focused on the task. No drive-by refactors.
- Prefer simple, readable code over clever abstractions. Add an abstraction only when there are at least two real uses.
- Follow existing patterns in the repo. If you think a pattern is wrong, say so and propose a change rather than silently diverging.
- Do not add a dependency without a clear reason. If you add one, record it in `techstack.md`.
- Never leave dead code, commented-out blocks, debug prints or unexplained TODOs.

### After coding
- Run the checks (section 6) and fix failures before saying you are done.
- Summarize what changed, what you verified, and anything left open. Be honest about what you did not test.
- Never claim something works unless you ran it.

## 4. Architecture Rules

- The frontend is a UI layer only. It never calls Groq or the database directly and holds no business logic.
- The backend is layered: `api` (thin routers) -> `services` (business logic) -> `models` and `db` (persistence). Routers do validation, auth and calling services, nothing else.
- All configuration comes from environment variables through `pydantic-settings`. No hardcoded keys, model names, thresholds, URLs or magic numbers.
- Ingestion always runs as a background task, never inside the request path. The endpoint returns a job id right away, job status lives in Postgres, and CPU heavy steps (parsing, embedding) run in a thread pool. On startup, mark any job left in `processing` as `failed` so it can be retried.
- The API is versioned under `/api/v1`. OpenAPI is the contract between frontend and backend. Generate frontend types from it with `openapi-typescript`, do not hand-write duplicates.
- Models are loaded once at startup (or lazily once), never per request.

## 5. RAG and AI Engineering Rules

These matter most for correctness. Treat them as non-negotiable.

### Grounding
- Answers must come only from retrieved KB context. The system prompt must instruct the model to answer from context only, say it does not know when context is insufficient, and never use outside knowledge.
- If no retrieved chunk passes the relevance threshold after reranking, return the "not found in knowledge base" fallback and do not call the LLM.
- Always return source citations (document title, page, snippet) with answers.
- Keep temperature low for answers.

### Retrieval pipeline
Follow this order: load recent turns, rewrite the question into a standalone query, embed, hybrid search (pgvector plus Postgres full text, merged with Reciprocal Rank Fusion), rerank, threshold check, generate, cite, persist.

### Embeddings
- Use the model's query instruction prompt for queries and none for documents.
- Normalize vectors and use cosine distance with an HNSW index.
- Store 1024 dimensional vectors (pgvector `vector` indexes up to 2000 dimensions).
- Store the embedding model name and dimension in a config table. If they change, trigger a full re-embed job, never mix vectors from different models.

### Chunking and ingestion
- Structure aware splitting (markdown headings first), 500 to 800 tokens, 10 to 15 percent overlap.
- Store `document_id`, `source`, `title`, `page`, `chunk_index` and a content hash.
- Updates are strictly incremental. Never re-ingest content that is already stored.
  - File level: store `file_hash` (SHA-256 of bytes), size and modified time per document. Same hash means skip the file with no parsing or embedding.
  - Chunk level: store `chunk_hash` (SHA-256 of normalized chunk text) per chunk. For a new or changed file, re-chunk it, then embed and insert only chunks whose hash is not already stored, delete stored chunks that no longer appear, and leave unchanged chunks and their vectors untouched.
  - Chunking must be deterministic and normalize text before hashing (whitespace, line endings), so formatting noise does not trigger re-embedding.
  - Identical chunk text may reuse an existing vector. A renamed or moved file with the same `file_hash` only updates its path.
  - Deleting a document removes only its chunks.
  - Only a change of embedding model or dimension re-embeds everything, and it must be an explicit admin action, never automatic.
- Ingestion jobs must be idempotent and report status (`pending`, `processing`, `done`, `failed`) with an error message on failure.
- Extract web pages with `trafilatura`, PDFs with `pymupdf4llm`, DOCX with `python-docx`.

### LLM calls
- Wrap every Groq call with a timeout, retry and exponential backoff (`tenacity`), and handle rate limit errors with a clear user facing message.
- Cache repeated identical questions in an in-process TTL cache where safe.
- Log latency and token usage for every call.
- Treat retrieved document text and user messages as untrusted. Guard against prompt injection: keep instructions in the system prompt, wrap context in clear delimiters, and tell the model that text inside the context is data, not instructions.

### Knowledge base import
- Build a CLI command (for example `uv run python -m app.cli ingest-folder`) that ingests every `.md` and `.pdf` under `KB_SOURCE_DIR` through the same pipeline the admin endpoints use.
- It must be idempotent and incremental as described above: running it twice in a row must embed nothing the second time, and adding one new file or editing part of one file must embed only the new chunks. Report counts of files skipped, added, updated and failed, and chunks added, removed and reused.
- Preserve the file name and relative path as metadata for citations.
- Inspect the actual files before choosing chunking details. Markdown files should split on headings, and PDFs may need table or layout handling. Adjust based on what the real documents look like.
- The assistant persona is a BRAC University information assistant. It must not answer general questions or questions about other universities, and the fallback message should say the answer was not found in the BRAC University knowledge base.

### Quality
- Maintain an evaluation set at `backend/tests/eval/` built from the real KB files, with sample questions, expected source documents, and out-of-scope questions that must trigger the fallback. Re-run it after any change to chunking, embeddings, retrieval, thresholds or prompts, and report the results.
- Tune the similarity threshold using this evaluation set, not by guessing.

## 6. Commands

Run from the repository root unless noted. Adjust here if the real scripts differ, and keep this section accurate.

```bash
# Services
# Windows: run `docker compose up -d` or `powershell -File scripts\setup_postgres.ps1`
# Linux: PostgreSQL with pgvector running locally or via Docker

# Windows All-in-One Quickstart (from root)
.\run_project.ps1

# Backend (from backend/)
uv sync
uv run uvicorn app.main:app --reload
uv run alembic upgrade head
uv run python -m app.cli ingest-folder    # bulk import KB_SOURCE_DIR
uv run alembic revision --autogenerate -m "describe change"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app

# Frontend (from frontend/)
bun install
bun run dev
bun run lint
bun run build
```

Definition of done for any change: lint, type check and tests pass for the area you touched, migrations apply cleanly, and the feature was exercised manually or by a test.

## 7. Code Standards

### Python
- Type hints on all functions. `mypy` must pass.
- Async all the way for I/O. Never block the event loop; run CPU heavy work (embedding, reranking, PDF parsing) in a thread pool.
- Every endpoint declares `response_model`, `tags`, `summary` and documented error responses.
- Use Pydantic schemas for all request and response bodies. Never return ORM objects directly.
- Raise typed domain exceptions in services and map them to HTTP errors in one place.
- Use dependency injection (`Depends`) for DB sessions, current user and role checks.
- Database changes always go through Alembic migrations. Never edit the schema by hand.

### TypeScript and Next.js
- Strict mode, no `any`, no unchecked type assertions.
- Server Components by default, Client Components only when interactivity requires it.
- Use `proxy.ts` for route protection (it replaces `middleware.ts` in Next 16). The backend remains the real authority on access.
- Fetch through one typed API client in `lib/`. Handle loading, error and empty states on every screen.
- Streaming chat uses `fetch` with `ReadableStream` for SSE. Handle aborts, reconnects and partial messages.
- Forms use React Hook Form with Zod. Render markdown safely and never use `dangerouslySetInnerHTML` with untrusted content.
- Accessible by default: labels, focus states, keyboard navigation, sensible contrast.

### General
- Names should explain intent. Functions do one thing. Keep files small.
- Comments explain why, not what.
- No em dashes in documentation or written text in this repo.

## 8. Security Rules

- Passwords hashed with argon2. Never store or log plaintext passwords.
- JWT access token (short lived) and refresh token in httpOnly, Secure, SameSite cookies. Never put tokens in localStorage.
- Role checks (`user`, `admin`) enforced server side with dependencies on every protected route. Document management endpoints are admin only.
- Users can only read and delete their own conversations.
- Validate uploads: allowed extensions and MIME types, size limit, safe filenames, no path traversal. Store files outside any publicly served directory.
- URL ingestion must guard against SSRF: allow only http and https, block private, loopback and link-local addresses, set timeouts and size limits.
- Rate limit auth and chat endpoints (`slowapi`, in-memory).
- Configure CORS with explicit origins, never a wildcard with credentials.
- Never commit secrets. Keep `.env.example` current with placeholder values only.
- Never log tokens, passwords, API keys or full document contents.

## 9. Logging Rules

- Use `structlog` with JSON output in production and readable output in development.
- A request ID middleware attaches an ID to every log line and returns it as `X-Request-ID`.
- Log: request method, path, status and latency, auth events, ingestion job lifecycle, retrieval scores and chosen chunks, fallback triggers, Groq latency and token usage, and errors with stack traces.
- Use correct levels: DEBUG for detail, INFO for normal events, WARNING for recoverable issues, ERROR for failures.
- No `print` statements.

## 10. Testing Rules

- Backend: `pytest`, `pytest-asyncio`, `httpx.AsyncClient`. Use a real local Postgres with pgvector for tests (a separate test database), not mocks of the database.
- Mock the Groq API in unit tests. Never call the real API in the test suite.
- Required coverage: auth flows, role enforcement, upload and URL ingestion, incremental ingestion (re-run embeds nothing, a new file or edited section embeds only new chunks, removed content deletes only its chunks), delete behavior, retrieval and threshold fallback, conversation memory and query rewrite, and error paths.
- Every bug fix gets a regression test.
- Frontend: type check, lint, and tests for critical flows (login, sending a message, admin upload) where practical.

## 11. Git and Workflow

- Small, focused commits with clear messages in the imperative mood (`Add document hash check to ingestion`).
- One logical change per commit. Do not mix refactors with features.
- Do not commit generated files, model weights, `.env`, uploads or build output. Keep `.gitignore` correct.
- Do not rewrite history or force push unless explicitly asked.
- Never run destructive commands (dropping databases, deleting volumes, `rm -rf` outside build dirs) without asking first.

## 12. Documentation Rules

- FastAPI Swagger and ReDoc must be complete and accurate. They are a graded deliverable. Add descriptions and examples to schemas and routes.
- Keep `README.md` current: what the project is, architecture, local setup (Postgres with pgvector, backend, frontend), environment variables, how to ingest knowledge, how to run tests.
- Update `techstack.md` and this file when decisions change.

## 13. Things to Avoid

- Do not answer from the model's own knowledge. Grounding failures are the worst bug in this project.
- Do not call the LLM when retrieval found nothing relevant.
- Do not put business logic in routers or in the frontend.
- Do not load embedding or reranker models per request.
- Do not run ingestion inside request handlers.
- Do not hardcode secrets, model names or thresholds.
- Do not invent API behavior, library functions or version features. If unsure, check the installed package source or official docs, or ask.
- Do not mark a task finished with failing checks or untested code paths.
- Do not over-engineer. This is a medium scale project, so avoid microservices, extra queues, or frameworks beyond `techstack.md`.

## 14. When You Are Unsure

State what you know, what you are assuming, and the options with trade-offs. Recommend one. Then proceed with the safest reasonable choice or ask a single precise question.
