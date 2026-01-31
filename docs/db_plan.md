# Database & RAG Implementation Plan

## 1. Status Overview
**Date:** January 17, 2026

We have successfully generated, validated, and structured the synthetic dataset for the Hotel Transylvania Voice AI project. The data is prepared for a "Hub-and-Spoke" RAG architecture.

### 1.1 Data Preparation (Complete)
*   **Raw Data:** Generated ~200 records of hotel policies, amenities, and location-specific details (`data/data_*.json`).
*   **Structured Data:** Partitioned into a production-ready folder structure:
    *   **Hub:** `data/prod/hub/global.json` (90 records) - Shared knowledge.
    *   **Spokes:** `data/prod/spokes/{tenant_id}.json` (35 records each for SF, NY, Chicago) - Tenant-specific data.
*   **Evaluation:** Created a "Gold Standard" QA dataset (`data/gold_standard_qa.json`) with 15 mixed-type questions (global retrieval, specific routing, negative constraints, and synthesis) to benchmark the system.

### 1.2 Infrastructure (In Progress)
*   **Docker:** Created `infra/docker/docker-compose.yml` configured for PostgreSQL 16 with the `pgvector` extension.

---

## 2. Architecture Decision

### 2.1 Database Choice: PostgreSQL + pgvector
We selected **PostgreSQL with pgvector** over a specialized vector database (like Pinecone or Qdrant) for the following reasons:
1.  **Hybrid Search:** Essential for the Hub-and-Spoke model. We need to perform vector similarity searches *strictly scoped* by a SQL filter (e.g., `WHERE tenant_id = 'sf' OR tenant_id IS NULL`).
2.  **Simplicity:** Reduces infrastructure complexity. We manage one database for both application state and vector embeddings.
3.  **Portability:** PGVector is supported by all major cloud providers (AWS RDS, Supabase, Neon), making the path to production trivial.
4.  **Cost & Dev Experience:** Self-hosted Docker container provides zero-latency, zero-cost local development.

### 2.2 Embedding Model (Proposed)
*   **Model:** `text-embedding-3-small` (OpenAI).
*   **Reason:** High performance, low cost, and standard industry benchmark.
*   **Dimensions:** 1536.

---

## 3. Implementation Roadmap

### Step 1: Database Initialization
*   **Action:** Start the Docker container.
*   **Verification:** Connect to the DB and enable the `vector` extension.

### Step 2: Schema Design
We will create a `knowledge_base` table with the following structure:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `TEXT` | Primary Key (e.g., `global_001`, `sf_002`) |
| `tenant_id` | `TEXT` | Nullable. If `NULL`, it is Global/Hub data. If set (e.g., `sf`), it is Spoke data. |
| `content` | `TEXT` | The actual text chunk to be retrieved. |
| `category` | `TEXT` | Metadata for pre-filtering (e.g., `policy`, `dining`). |
| `metadata` | `JSONB` | flexible JSON bag for extra attributes (e.g., `{ "type": "dragon_safety" }`). |
| `embedding` | `VECTOR(1536)` | The semantic vector representation of `content`. |

### Step 3: Ingestion Pipeline
Develop a Python script (`scripts/ingest_data.py`) to:
1.  Iterate through `data/prod/hub` and `data/prod/spokes`.
2.  Generate embeddings for each text chunk using OpenAI API.
3.  Upsert records into the Postgres table.
4.  Handle `tenant_id` assignment correctly based on the file source.

### Step 4: Retrieval Logic (The "Router")
Implement the core Hub-and-Spoke logic:
*   **Query:** "What time is check-in?" (Context: User is calling San Francisco).
*   **SQL Logic:**
    ```sql
    SELECT content
    FROM knowledge_base
    WHERE (tenant_id = 'sf' OR tenant_id IS NULL)
    ORDER BY embedding <=> query_vector
    LIMIT 3;
    ```
*   **Ranking:** Ensure local spoke data can override or coexist with global hub data.

### Step 5: Evaluation
Run the automated test suite using `data/gold_standard_qa.json`:
1.  Feed questions to the RAG pipeline.
2.  Compare retrieved context against `ground_truth`.
3.  Calculate success rate (Faithfulness & Relevance).
