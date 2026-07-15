# RAG Research API: Project Overview

## 1. Problem and Goal

**What:** A backend service that ingests documents or URLs, stores them as searchable vector embeddings, and answers natural-language questions against that content with cited sources.

**Why this project:** It compresses ConneqtedAgents' own product pattern (their financial-research AI pulls data from multiple sources and condenses it) into a buildable 7-day scope, while exercising every "good to have" line in their JD: FastAPI, PostgreSQL, vector embeddings, LLM API integration, data pipelines, and Docker deployment.

---

## 2. Architecture at a Glance

Data flow, end to end:

1. Client submits a document (file or URL).
2. Ingestion service extracts and cleans raw text.
3. Text is split into chunks.
4. Each chunk is sent to an embedding API; a vector comes back.
5. Chunk text, vector, and metadata are stored in Postgres.
6. Client submits a question.
7. The question is embedded with the same model.
8. A similarity search against stored vectors returns the top-k relevant chunks.
9. Those chunks plus the question are passed to an LLM as context.
10. The LLM generates an answer and references which chunks it drew from.
11. The API returns the answer alongside the source chunks used.

Components: API Layer (FastAPI) → Ingestion Service → Embedding Service → Vector Store (Postgres + pgvector) → Retrieval Layer → Generation Layer (LLM) → Client.

---

## 3. Architectural Decisions (What, Why, How)

### 3.1 Framework: FastAPI

- **What:** FastAPI as the sole web framework, no Django.
- **Why:** The role is FastAPI-specific. Django REST Framework already proves REST competency from prior work; this project needs to prove the framework named in the JD. FastAPI's native async support also matters here, since embedding calls and LLM calls are both I/O-bound network requests that benefit from non-blocking handling.
- **How:** Async path operations for every endpoint that calls an external API (embedding, generation). Pydantic models define request and response schemas, which also gives free request validation, something DRF serializers do but FastAPI ties directly into the OpenAPI docs.

### 3.2 Data Store: PostgreSQL + pgvector, not a dedicated vector DB

- **What:** A single Postgres instance holds relational data (documents, chunks, metadata) and vector embeddings together, using the pgvector extension.
- **Why:** Dedicated vector databases (Pinecone, Weaviate, Qdrant) add a second system to operate, deploy, and pay for. For a project of this scale, one database is easier to reason about and to explain in an interview: fewer moving parts, one connection pool, one backup story. pgvector is also the same technology already used on the LangGraph/agents engagement, so this reinforces existing, provable experience rather than introducing a new unknown.
- **How:** The `chunks` table stores an embedding column with a fixed dimensionality matching the embedding model's output. Similarity search happens via a distance operator (cosine distance) directly in a SQL query, no separate retrieval service needed.

### 3.3 Chunking Strategy

- **What:** Structure-aware chunking: split first on paragraph and sentence boundaries, fall back to a fixed token window only when a paragraph is too long, with a small overlap between adjacent chunks.
- **Why:** Naive fixed-size chunking (e.g. every 500 tokens regardless of sentence boundaries) frequently cuts a sentence or idea in half, which weakens both the embedding quality and the LLM's ability to answer from a chunk in isolation. Overlap protects against relevant information sitting exactly on a chunk boundary.
- **How:** Chunk size and overlap become configurable parameters (not hardcoded), so the same ingestion path can be tuned per document type without a redeploy.

### 3.4 Embedding Model

- **What:** A hosted embedding API rather than a self-hosted open-source model.
- **Why:** Claude does not expose a native embeddings endpoint, so the two realistic choices are OpenAI's `text-embedding-3-small` or Voyage AI (Anthropic's recommended embedding partner). Either is cheap, requires no GPU, and keeps the project's infrastructure footprint small. Self-hosted embedding models (e.g. sentence-transformers) avoid API cost but add deployment complexity that isn't the point of this project.
- **How:** Embedding calls are isolated behind a single internal function, so the model can be swapped later without touching ingestion or retrieval logic.

### 3.5 Vector Index Type: HNSW over IVFFlat

- **What:** An HNSW index on the embedding column, not IVFFlat.
- **Why:** IVFFlat needs the table populated and analyzed before the index gives good recall, and its accuracy is sensitive to a tuned `lists` parameter. HNSW gives strong recall out of the box and doesn't require a pre-existing data distribution to tune against, which matters for a project where the corpus size will be small and will change during development.
- **How:** Trade-off to state explicitly in the interview: HNSW builds slower and uses more memory per index than IVFFlat, an acceptable cost at this data scale, but the wrong default for a table with millions of rows without capacity planning.

### 3.6 Generation Model and Citation Handling

- **What:** A separate LLM call (Claude or GPT) takes the retrieved chunks and the original question, and produces both an answer and a list of which chunks it relied on.
- **Why:** Returning an answer with no traceable source is the main trust problem with RAG systems. Citations let a caller verify the answer against the original text instead of taking the model's output on faith, mirroring what a research product needs.
- **How:** Each chunk carries a stable identifier before being sent as context. The generation prompt instructs the model to reference chunk identifiers inline, and the API response maps those identifiers back to document titles and excerpts.

### 3.7 Ingestion: Async Background Processing

- **What:** Document ingestion (extraction, chunking, embedding, storage) runs as a background task, not inline in the request/response cycle.
- **Why:** Embedding a large document can take several seconds to minutes depending on size. Blocking the HTTP request for that long is poor API design and doesn't reflect production practice.
- **How:** The ingestion endpoint returns immediately with a document ID and a status field. A separate status endpoint reports progress (queued, processing, ready, failed), so the client polls rather than waits.

### 3.8 Auth and Rate Limiting

- **What:** A simple API key check on every endpoint, plus basic per-key rate limiting.
- **Why:** Full auth (OAuth, user accounts) is out of scope for a 7-day demo project and would consume time better spent on the RAG pipeline itself. An API key is the minimum that still demonstrates security-consciousness, which the JD explicitly lists as a responsibility ("optimize application performance, security, and reliability").
- **How:** Key checked via a dependency injected into each route. Rate limiting tracked per key in-memory or in Postgres, sufficient for demo traffic.

### 3.9 Deployment

- **What:** The whole service (API + Postgres) defined in Docker Compose, deployed to a free-tier host (Render, Railway, or Fly.io).
- **Why:** Docker is explicitly listed in the JD's "good to have" section. Docker Compose also lets the project be cloned and run locally in one command, which matters when the interviewer wants to actually see it work.
- **How:** One service for the FastAPI app, one for Postgres with the pgvector extension pre-installed, environment variables for API keys and connection strings, no secrets committed to the repo.

---

## 4. Data Model

**documents**

| Field            | Purpose                              |
| ---------------- | ------------------------------------ |
| id               | Primary key                          |
| source_type      | file or url                          |
| source_reference | Original filename or URL             |
| title            | Display title                        |
| status           | queued / processing / ready / failed |
| created_at       | Ingestion timestamp                  |

**chunks**

| Field       | Purpose                             |
| ----------- | ----------------------------------- |
| id          | Primary key                         |
| document_id | Foreign key to documents            |
| chunk_index | Position within the source document |
| content     | Raw chunk text                      |
| token_count | Size of the chunk                   |
| embedding   | Vector representation               |
| created_at  | Timestamp                           |

**query_logs** (optional, useful for the benchmark numbers mentioned in section 7)

| Field               | Purpose                  |
| ------------------- | ------------------------ |
| id                  | Primary key              |
| query_text          | The question asked       |
| retrieved_chunk_ids | Which chunks were used   |
| answer              | Generated answer         |
| latency_ms          | End-to-end response time |
| created_at          | Timestamp                |

---

## 5. API Surface

| Method | Path            | Purpose                                                                      |
| ------ | --------------- | ---------------------------------------------------------------------------- |
| POST   | /documents      | Submit a file or URL for ingestion; returns a document ID and initial status |
| GET    | /documents/{id} | Check ingestion status of a document                                         |
| POST   | /query          | Submit a question; returns an answer and the source chunks used              |
| GET    | /health         | Basic liveness check for deployment monitoring                               |

---

## 6. Trade-offs Considered

| Decision                 | Alternative Considered               | Why Rejected (for this project's scope)                                 |
| ------------------------ | ------------------------------------ | ----------------------------------------------------------------------- |
| Postgres + pgvector      | Pinecone / Weaviate / Qdrant         | Extra system to deploy and pay for; not needed at this data scale       |
| HNSW index               | IVFFlat index                        | Needs pre-tuned `lists` parameter and a populated table to perform well |
| Structure-aware chunking | Naive fixed-token chunking           | Cuts sentences mid-thought, weakens embedding and answer quality        |
| Hosted embedding API     | Self-hosted embedding model          | Avoids GPU/infra overhead not central to the interview goal             |
| Background ingestion     | Synchronous ingestion in the request | Blocks the client for the duration of embedding, poor API design        |
| API key auth             | Full OAuth/user accounts             | Out of scope for a 7-day demo; time better spent on the RAG pipeline    |

---

## 7. Metrics to Capture

These turn the project from "I built a thing" into "I built a thing and can defend its performance":

- Ingestion throughput (documents or pages per minute)
- Average query latency, broken into retrieval time vs generation time
- Embedding cost per document (token count × API price)
- Index build time at whatever corpus size is tested
- Recall quality on a small hand-labeled set of test questions (does the retrieved chunk actually contain the answer)

---

## 8. Build Sequence Reference

| Day | Focus                                                                  |
| --- | ---------------------------------------------------------------------- |
| 1   | FastAPI skeleton, Docker Compose with Postgres + pgvector, core tables |
| 2   | Ingestion endpoint: extraction and chunking                            |
| 3   | Embedding pipeline and vector storage, index creation                  |
| 4   | Query endpoint: embed query, similarity search                         |
| 5   | Answer generation with citation mapping                                |
| 6   | Auth, rate limiting, error handling, tests                             |
| 7   | Dockerize fully, deploy, write README with benchmarks                  |

---

## 9. Interview Talking Points

- Why one database (Postgres + pgvector) instead of a dedicated vector store, and when that choice would stop being correct (data scale where it would).
- HNSW vs IVFFlat, and that the decision was scale-dependent, not universal.
- Why ingestion is async and what would break if it weren't.
- How citations are tracked back to source chunks, and why that matters for trust in a research tool.
- Actual measured numbers: latency, throughput, cost per query, not estimates.
