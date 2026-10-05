# Tech Stack: BRAC University Information Chatbot (RAG)

This file is the source of truth for technology choices. Claude Code should follow it when scaffolding and implementing the project. If a choice needs to change, update this file first.

## 1. Project Summary

A chatbot that answers only from a custom, medium size knowledge base (KB). It supports PDF, text, markdown, DOCX and web page sources, keeps short-term conversation memory per session, and updates the KB without retraining. Users get a chat interface. Admins manage knowledge and users. Frontend and backend are separate and communicate only through a documented REST API (plus SSE for streaming).

### Project and Knowledge Base

The project is the **BRAC University Information Chatbot**. It answers questions about BRAC University using only its own knowledge base.

The KB is already prepared and stored locally in a folder as **markdown (.md) files and PDF files**. Do not scrape or invent content for it.
- The folder path is set with `KB_SOURCE_DIR` (see environment variables).
- Provide a bulk import command (a CLI script in the backend) that walks `KB_SOURCE_DIR`, ingests every `.md` and `.pdf` file, and is safe to re-run. Anything already ingested is never re-ingested. Only new files, and only the new or changed parts of modified files, are processed (see "Incremental Ingestion" in section 4.2).
- The admin upload and URL ingest endpoints still work for adding more content later, using the same ingestion pipeline.
- Keep the original file name and relative path as document metadata so citations can show the source file.
- The fallback reply should mention that the answer was not found in the BRAC University knowledge base.

## 2. Architecture Overview

```
Next.js 16.3.7 (UI only)  --HTTPS/JSON + SSE-->  FastAPI (all business logic)
                                                |
                         +----------------------+----------------------+
                         |                                             |
                  PostgreSQL + pgvector + FAISS                  Groq API (LLM)
                  (users, chats, docs,                           Local models
                   chunks, vectors, job status)                  (embedding, reranker)
```

Rules:
- The frontend contains no business logic and never calls Groq or the database directly.
- Every capability is exposed as an API endpoint with a Pydantic schema.
- Ingestion runs as a background task (FastAPI `BackgroundTasks`), never inside the request path. The endpoint returns immediately with a job id, and job status is stored in Postgres.

## 3. Fixed Choices

| Layer | Choice | Notes |
|---|---|---|
| Backend framework | FastAPI 0.142.2 (Python 3.12) | Async, auto-generated OpenAPI docs |
| Frontend framework | Next.js 16.3.7 with TypeScript (strict) | App Router. Use `proxy.ts` (replaces `middleware.ts` in Next 16) for route protection |
| Database | PostgreSQL 18.6 | With the pgvector extension |
| JS runtime and package manager | Bun 1.4.2 | Used for installs, scripts and running the frontend toolchain |
| LLM provider | Groq API | Chat completion and streaming |
| API documentation | FastAPI Swagger UI and ReDoc | Fill in tags, summaries, descriptions, response models and examples on every route |

### Pinned Versions

| Technology | Version |
|---|---|
| PostgreSQL | 18.6 |
| Next.js | 16.3.7 |
| FastAPI | 0.142.2 |
| Bun | 1.4.2 |

Pin these exact versions in `pyproject.toml`, `package.json` (and `bun.lock`) and any other version references. Do not use floating versions like `latest`.

## 4. Recommended Choices

### 4.1 Retrieval and AI

| Concern | Choice | Notes |
|---|---|---|
| Embedding model | **sentence-transformers/all-MiniLM-L6-v2** | Lightweight 384-dimensional SentenceTransformers model, suitable for fast CPU ingestion and queries |
| Embedding upgrade path | A larger SentenceTransformers model | Any replacement requires changing `EMBEDDING_DIM`, running its migration, and re-ingesting the corpus |
| Lightweight alternative | google/embeddinggemma-300m | Use only if CPU or RAM is very limited. Check its license terms before use |
| Reranker | **cross-encoder/ms-marco-MiniLM-L-6-v2** | Lightweight SentenceTransformers cross-encoder for reranking the top retrieved chunks |
| Vector store | **FAISS CPU over embeddings stored in PostgreSQL** | FAISS inner-product search over normalized vectors. PostgreSQL remains the source of truth for vectors, metadata, users and chat history |
| Hybrid search | FAISS plus Postgres full-text search, merged with Reciprocal Rank Fusion | Improves semantic matching and exact term/name matching |
| LLM (answers) | Groq, a large Llama class model | Pick from Groq's current model list at build time. Keep the model name in config |
| LLM (query rewrite) | Groq, a small fast model | Used for turning follow-ups into standalone questions |
| Orchestration | LangChain (components only) | Document loaders, text splitters, `langchain-groq`. Keep the pipeline in plain readable Python, no heavy agent chains |

Embedding notes for the implementer:
- Use the model's query instruction prompt for queries and no instruction for documents.
- Store 384 dimensional vectors in PostgreSQL. FAISS searches normalized 384-dimensional vectors with inner product, equivalent to cosine similarity.
- Normalize vectors and use cosine distance.
- Record the embedding model name and dimension in a config table so a future model swap triggers a re-embed job.

### 4.2 Ingestion (multiple formats)

| Source | Library |
|---|---|
| PDF | `pymupdf4llm` (PyMuPDF), keeps headings and tables as markdown |
| DOCX | `python-docx` |
| TXT and MD | Plain loaders |
| Web pages | `httpx` plus `trafilatura` for clean main content extraction |

Chunking: 500 to 800 tokens, 10 to 15 percent overlap, structure aware splitting on markdown headings first. Store `document_id`, `source`, `title`, `page` and `chunk_index` as metadata.

#### Incremental Ingestion (no re-ingesting what already exists)

Ingestion must be incremental at two levels, so adding new knowledge only costs the new part.

1. **File level.** Store `source_path`, `file_hash` (SHA-256 of the file bytes), size and modified time per document. On each run, if the path exists and the hash matches, skip the file entirely. No parsing, no embedding.
2. **Chunk level.** Store a `chunk_hash` (SHA-256 of the normalized chunk text) on every chunk. When a file is new or its hash changed:
   - Parse and chunk it again (cheap).
   - Compare the new chunk hashes with the stored ones for that document.
   - Embed and insert only chunks whose hash is not already stored.
   - Delete stored chunks whose hash no longer appears in the file.
   - Keep unchanged chunks and their existing vectors untouched.

Supporting rules:
- Chunking must be deterministic (same input gives same chunks), with markdown heading based splitting so that adding a section does not shift every other chunk boundary.
- Normalize text before hashing (trim whitespace, normalize line endings) so trivial formatting noise does not cause re-embedding.
- Identical chunk text appearing in several documents may reuse the existing vector instead of calling the embedding model again.
- Renamed or moved files with the same `file_hash` update the path only and do not re-embed.
- Deleting a file or document removes only its chunks.
- The only reason to re-embed everything is a change of embedding model or dimension, which is an explicit admin action, never automatic.
- Every ingestion run reports counts: files skipped, files added, files updated, chunks added, chunks removed, chunks reused.

### 4.3 Backend

| Concern | Choice |
|---|---|
| Validation and settings | Pydantic v2, `pydantic-settings` |
| Database access | SQLAlchemy 2.0 (async) with `asyncpg` |
| Migrations | Alembic |
| Background jobs | **FastAPI `BackgroundTasks`**, with job status persisted in Postgres. CPU heavy work (parsing, embedding) runs in a thread pool so the event loop stays free |
| Cache | In-process TTL cache (`cachetools`) for repeated questions |
| Rate limiting | `slowapi` with in-memory storage |
| HTTP client | `httpx` (async) |
| Retry and backoff | `tenacity` around Groq calls to handle rate limits |
| Streaming | Server-Sent Events through `StreamingResponse` |
| Testing | `pytest`, `pytest-asyncio`, `httpx.AsyncClient` |
| Linting and typing | `ruff`, `mypy` |
| Package manager | `uv` |

### 4.4 Authentication and Authorization

- JWT access token (short lived) and refresh token (longer lived), stored in httpOnly, Secure, SameSite cookies.
- Password hashing with **argon2** (`argon2-cffi`).
- Roles: `user` and `admin`, enforced with FastAPI dependencies.
- Admin only: upload documents, ingest URLs, list and delete documents, re-index, manage users, view logs.
- User: chat and view own conversation history.
- Next.js `proxy.ts` handles redirect for unauthenticated users. The backend remains the real authority for access control.

### 4.5 Logging

- `structlog` with JSON output.
- Request ID middleware, attached to every log line and returned in an `X-Request-ID` header.
- Log: requests (method, path, status, latency), auth events, ingestion jobs, retrieval scores, LLM latency and token usage, errors with stack traces.
- Never log passwords, tokens or full document contents.
- Console output in development, rotating file handler in production.

### 4.6 Frontend

| Concern | Choice |
|---|---|
| Language | TypeScript (strict mode) |
| Styling | Tailwind CSS v4 |
| Components | shadcn/ui |
| Server state | TanStack Query |
| Streaming | `fetch` with `ReadableStream` to consume SSE, or Vercel AI SDK |
| Forms and validation | React Hook Form with Zod |
| Markdown rendering | `react-markdown` with `remark-gfm` |
| Icons | `lucide-react` |
| API types | Generated from FastAPI's OpenAPI schema with `openapi-typescript` |
| Package manager | Bun 1.4.2 (`bun install`, `bun run`) |

Pages:
- `/login` and `/register`
- `/chat` (conversation list, streaming messages, source citations)
- `/admin/knowledge` (upload, URL ingest, document table, delete, re-index, ingestion status)
- `/admin/users` (optional)

### 4.7 DevOps

- No containerization and no Redis for now. Run everything locally: `api` (uvicorn) and `web` (Next.js), plus locally installed PostgreSQL 18.6 with the pgvector extension and FAISS CPU.
- Docker and Redis can be added later, but do not create Dockerfiles, Compose files or Redis-dependent code unless asked.
- `.env.example` committed, real secrets never committed.
- GitHub Actions for lint and test (optional).
- Embedding and reranker model weights are cached in the default Hugging Face cache directory (or `HF_HOME`) so they download only once.

## 5. Requirement to Stack Mapping

| Requirement | How it is met |
|---|---|
| Trainable on custom medium size KB | Ingestion pipeline (no training), chunks and vectors in PostgreSQL, FAISS dense retrieval |
| Answers only from KB | Retrieval, rerank, similarity threshold, strict system prompt, citations |
| Graceful out-of-scope handling | If no chunk passes the threshold, return a "not found in knowledge base" reply without calling the LLM. If the question is ambiguous, ask for clarification |
| Intelligent retrieval, context aware | Query rewrite with chat history, hybrid search, reranker |
| Conversation memory | Messages stored per session in Postgres, last N turns sent to the LLM |
| Multiple data formats | PyMuPDF, python-docx, text loaders, trafilatura |
| KB updates without retraining | File hash plus chunk hash, embed only new or changed chunks, delete by `document_id`, URL re-crawl |
| Authentication for users and admins | JWT in httpOnly cookies, argon2, role based dependencies |
| API documentation | FastAPI Swagger UI and ReDoc, plus a short README |
| Backend logger | structlog JSON logs with request IDs |
| Complete frontend | Next.js 16.3.7 chat UI and admin UI |
| Backend for queries, KB and generation | FastAPI services layer |
| Clean API based architecture | Versioned REST API under `/api/v1`, OpenAPI as the contract |

## 6. Answer Pipeline

1. Receive the user message and `session_id`.
2. Load the last N turns for that session.
3. Rewrite the message into a standalone question (small Groq model).
4. Embed the query and run FAISS plus full-text hybrid retrieval.
5. Rerank and keep the top 4 to 6.
6. If the best reranker score is below the threshold, stream the fallback message and stop.
7. Otherwise build the prompt with strict instructions and retrieved chunks, then stream the Groq response.
8. Return citations (document title, page, snippet) with the final message.
9. Persist the user message, assistant message and sources.

System prompt rules: answer only from the provided context, say you do not know when the context is insufficient, do not use outside knowledge, cite sources.

## 7. Suggested Repository Layout

```
repo/
  .env.example
  techstack.md
  README.md
  backend/
    pyproject.toml
    alembic/
    app/
      main.py
      api/v1/          (auth.py, chat.py, documents.py, users.py, health.py)
      core/            (config.py, security.py, logging.py, deps.py)
      services/        (ingestion/, retrieval/, llm/, memory/, auth/)
      models/          (SQLAlchemy models)
      schemas/         (Pydantic schemas)
      db/              (session, base)
      tasks/           (background ingestion tasks)
    tests/
  frontend/
    package.json
    proxy.ts
    app/
      (auth)/login, register
      chat/
      admin/knowledge, users
    components/
    lib/               (api client, generated types)
```

## 8. Core API Endpoints (v1)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Chat | `POST /chat/stream` (SSE), `GET /chat/sessions`, `GET /chat/sessions/{id}`, `DELETE /chat/sessions/{id}` |
| Documents (admin) | `POST /documents/upload`, `POST /documents/url`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`, `POST /documents/{id}/reindex` |
| System | `GET /health`, `GET /docs`, `GET /redoc` |

## 9. Conventions for Claude Code

- Type hints everywhere in Python. TypeScript strict mode in the frontend, no `any`.
- Business logic lives in `services/`, routers stay thin.
- All configuration comes from environment variables through `pydantic-settings`. Do not hardcode model names, thresholds or keys.
- Every endpoint declares `response_model`, tags, summary and error responses.
- Wrap every Groq call with retry and backoff and a timeout.
- Write tests for auth, role enforcement, ingestion, retrieval threshold behavior and the fallback path.
- Keep files small and functions focused. Prefer clear code over clever abstractions.
- Do not add new libraries without a reason. If one is needed, add it to this file.

## 10. Environment Variables (starting set)

```
DATABASE_URL=
GROQ_API_KEY=
GROQ_ANSWER_MODEL=openai/gpt-oss-120b
GROQ_REWRITE_MODEL=openai/gpt-oss-20b
GROQ_REASONING_EFFORT=medium
GROQ_MAX_COMPLETION_TOKENS=1200
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RETRIEVAL_TOP_K=10
RERANK_TOP_N=5
SIMILARITY_THRESHOLD=
CHAT_HISTORY_TURNS=6
KB_SOURCE_DIR=
JWT_SECRET=
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
CORS_ORIGINS=http://localhost:3000
```

## 11. Build Order

1. Project skeleton, config, logging, health endpoint, local Postgres with pgvector and FAISS setup.
2. Database models, Alembic, auth with roles.
3. Ingestion pipeline (text and PDF first, then DOCX and URL), embeddings, PostgreSQL storage and FAISS retrieval.
4. Retrieval, rerank, threshold fallback, Groq streaming answer.
5. Conversation memory and query rewrite.
6. Frontend: auth, chat UI with streaming and citations.
7. Admin knowledge UI, update and delete flows.
8. Tests, API docs polish, README, evaluation set of sample questions.
