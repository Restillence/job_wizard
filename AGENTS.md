# JobWiz Architecture & Execution Plan

> **For AI Assistant:** REQUIRED: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build a robust, scalable, GDPR-compliant MVP for an AI-powered B2C Job Application Assistant.

**Architecture:** API-first, Synchronous-First/Scale-Later methodology.

**Tech Stack:** Python 3.12+ (in `jobwiz_env` conda env), FastAPI, SQLAlchemy 2.0, Pydantic 2.0, PostgreSQL (with pg_trgm extension), HTTPX, Crawl4AI, OpenAI Embeddings, Pytest.

---

## 1. Build/Lint/Test Commands

```bash
conda activate jobwiz_env

# Testing
pytest tests/
pytest tests/test_api/test_applications.py -v
pytest --cov=src tests/

# Linting & Formatting
ruff check .
ruff format .

# Type checking
mypy src/

# Database reset (after schema changes)
python -c "from src.database import engine; from src.models import Base; Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)" && python init_db.py
```

---

## 2. Code Style & Guidelines

* **Imports:** Grouped (Standard library, Third-party, Local). Managed by `ruff`.
* **Formatting:** `ruff format` defaults (line length 88).
* **Typing:** Strict type hinting required. Use `mypy` for validation.
* **Naming:** `snake_case` (variables/functions), `PascalCase` (classes), `UPPER_SNAKE_CASE` (constants).
* **Error Handling:** Use `HTTPException` for API boundaries. Custom exceptions for domain logic.
* **Dependency Injection:** Use `Depends` for DB sessions, config, and external services.
* **Security:** All protected endpoints MUST use `Depends(verify_jwt)` and `Depends(check_rate_limit)`.
* **Synchronous First:** No `asyncio` unless required by framework/library. No Celery/Redis until MVP validation.

---

## 3. Database Schema

PostgreSQL with SQLAlchemy 2.0. **Enable pg_trgm extension for fuzzy search.**

### CompanySize (Enum)
* `startup`
* `hidden_champion`
* `enterprise`

### Users
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary Key |
| `email` | String | Unique, Indexed |
| `hashed_password` | String | |
| `created_at` | DateTime (UTC) | |
| `zusatz_infos` | JSONB | **Critical**: Stores manually added skills/interests for vector matching |
| `subscription_tier` | String | Default: 'free' |
| `payment_customer_id` | String | Nullable, for Stripe |
| `credits_used` | Integer | Default: 0 |
| `credits_limit` | Integer | Default: 10 |
| `last_reset_date` | DateTime (UTC) | |
| `is_superuser` | Boolean | Default: False |

### Companies
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary Key |
| `name` | String | Indexed |
| `city` | String | Nullable |
| `industry` | String | Nullable |
| `company_size` | Enum | `startup`, `hidden_champion`, `enterprise` |
| `url` | String | Career page URL, Unique |
| `created_at` | DateTime (UTC) | |

### Jobs
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary Key |
| `company_id` | UUID | FK → Companies.id |
| `source_url` | String | Unique, Indexed |
| `title` | String | |
| `description` | Text | |
| `extracted_requirements` | JSONB | Parsed via AI/Scraper |
| `embedding` | JSON | OpenAI text-embedding-3-small (1536 floats, stored as JSON) |
| `is_active` | Boolean | Default: True (soft-delete for removed jobs) |
| `first_seen_at` | DateTime (UTC) | When first discovered |
| `last_seen_at` | DateTime (UTC) | Last confirmed active |
| `created_at` | DateTime (UTC) | |

### Resumes
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary Key |
| `user_id` | UUID | FK → Users.id |
| `file_path` | String | Relative path |
| `embedding` | JSON | Pre-computed user profile embedding (1536 floats) |
| `created_at` | DateTime (UTC) | |

### Applications
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary Key |
| `user_id` | UUID | FK → Users.id |
| `job_id` | UUID | FK → Jobs.id |
| `status` | Enum | `Drafted`, `Approved`, `Sent`, `Rejected` |
| `ai_match_rationale` | Text | EU AI Act logging |
| `cover_letter_file_path` | String | Relative path, Nullable |
| `similarity_score` | Float | Cosine similarity at match time |
| `created_at` | DateTime (UTC) | |
| `updated_at` | DateTime (UTC) | |

---

## 4. API Endpoints

### Separate Endpoints (Granular Control)

#### `POST /api/v1/companies/search`
Search local companies with fuzzy matching. Triggers self-building logic if results below threshold.

**Query Params (all Optional):**
* `city`: Filter by city
* `industry`: Filter by industry
* `keywords`: Fuzzy search on company name
* `company_size`: Filter by enum (`startup`, `hidden_champion`, `enterprise`)

**Logic:**
1. Query local Companies table with pg_trgm fuzzy search
2. Calculate dynamic threshold based on query specificity:
   - Broad query (all params empty): `MIN_RESULTS_THRESHOLD = 50`
   - Specific query (any filter provided): `MIN_RESULTS_THRESHOLD = 5`
3. If count < threshold → trigger ONE-TIME search API fallback with exclusion prompting
4. Save new companies to DB, return combined results

**Response:**
```json
{
  "companies": [...],
  "total_found": 15,
  "newly_added": 3,
  "source": "local" | "api_fallback"
}
```

#### `POST /api/v1/jobs/extract`
Extract jobs from specified company career pages.

**Body:**
```json
{
  "company_ids": ["uuid1", "uuid2"]
}
```

**Logic:**
1. For each company, run Hybrid Extraction Engine
2. **Step A (ATS Fast Path):** Check URL against known footprints (Personio, Workday, Greenhouse). Extract via HTTPX JSON APIs.
3. **Step B (Fallback):** Use Crawl4AI for custom sites.
4. **Upsert Logic:**
   - If job exists (by `source_url`): update `last_seen_at`, `is_active = True`
   - If new: insert with `first_seen_at = now()`, generate embedding
5. Return extracted jobs

**Response:**
```json
{
  "jobs": [...],
  "total_extracted": 47,
  "newly_added": 12,
  "updated": 35
}
```

#### `POST /api/v1/jobs/match`
Vector match user profile against jobs.

**Body:**
```json
{
  "user_id": "uuid",
  "company_ids": ["uuid1"],  // optional filter
  "top_k": 20
}
```

**Logic:**
1. Get user's resume embedding (or generate from CV + zusatz_infos)
2. Compute cosine similarity against job embeddings
3. Return ranked job list with similarity scores
4. **DO NOT generate cover letters yet** (JIT pattern)

**Response:**
```json
{
  "matched_jobs": [
    {
      "job_id": "uuid",
      "title": "Senior Python Developer",
      "company_name": "TechCorp",
      "similarity_score": 0.87,
      "is_new_match": true
    }
  ],
  "total_matches": 15
}
```

#### `POST /api/v1/applications/prepare`
**JIT Trigger** - Only called when user clicks "Prepare Application".

**Body:**
```json
{
  "user_id": "uuid",
  "job_id": "uuid"
}
```

**Logic:**
1. Strip PII from resume (GDPR)
2. Dynamically tailor resume to job keywords
3. Generate cover letter via LLM
4. Log AI match rationale (EU AI Act)
5. Save to Applications table with status `Drafted`
6. Return draft for review

**Response:**
```json
{
  "application_id": "uuid",
  "cover_letter_path": "uploads/cover_letters/uuid.txt",
  "ai_match_rationale": "User matches 4/5 requirements...",
  "status": "Drafted"
}
```

#### `POST /api/v1/applications/{app_id}/approve`
Human-in-the-loop approval. Changes status to `Approved`.

#### `POST /api/v1/resumes/upload`
Upload PDF/Docx, strip PII, generate embedding, save to local storage.

### Combined Endpoint (Convenience)

#### `POST /api/v1/pipeline/search-and-match`
One-shot job discovery with matching.

**Body:**
```json
{
  "city": "Berlin",           // optional
  "industry": "AI",           // optional
  "keywords": ["python"],     // optional
  "company_size": "startup",  // optional
  "user_id": "uuid",
  "top_k": 20
}
```

**Internal Flow:**
1. Call `/companies/search` logic
2. Call `/jobs/extract` logic for found companies
3. Call `/jobs/match` logic for user
4. Return combined results

**Response:**
```json
{
  "companies_found": 15,
  "companies_new": 3,
  "jobs_extracted": 47,
  "jobs_new": 12,
  "matched_jobs": [
    {
      "job_id": "uuid",
      "title": "Senior Python Developer",
      "company_name": "TechCorp",
      "similarity_score": 0.87
    }
  ]
}
```

---

## 5. Self-Building Discovery Logic

```
MIN_RESULTS_THRESHOLD:
  - Broad query (no filters): 50 companies
  - Specific query (any filter): 5 companies

EXCLUSION PROMPTING:
When calling search API (Tavily/Serper/Brave/DDG):
  "Find 20 companies matching [query], but EXCLUDE companies:
   [Company A, Company B, Company C, ...existing DB names...]"
  
  This guarantees continuous DB growth without duplicates.
```

---

## 6. Hybrid Extraction Engine

**ATS Fast Path (HTTPX):**
| ATS | URL Pattern | Extraction Method |
|-----|-------------|-------------------|
| Personio | `personio.de` | Hidden JSON API |
| Workday | `workday.com` | JSON endpoint |
| Greenhouse | `greenhouse.io` | JSON API |

**Fallback (Crawl4AI):**
1. Navigate to career page
2. Extract markdown
3. Pass to LLM with `JobSchema` structured output
4. Validate with Pydantic

---

## 7. Vector RAG Pipeline

**Embedding Model:** `text-embedding-3-small` (1536 dimensions)

**Pre-compute on:**
* Resume upload → store on Resume.embedding
* Job extraction → store on Job.embedding

**Query Flow:**
1. User profile = CV text + zusatz_infos (skills, interests)
2. Embed profile (one-time, cached on Resume)
3. Cosine similarity: `dot(a, b) / (norm(a) * norm(b))`
4. Return top-k ranked jobs

---

## 8. CORS Configuration (Phase 2)

```python
# src/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 9. Phased Execution Plan

### Phase 1: Schema Migration
* Add `Company` model with `CompanySizeEnum`
* Modify `Job` to use `company_id` FK
* Add `is_active`, `first_seen_at`, `last_seen_at`, `embedding` to Jobs
* Add `embedding` to Resumes
* Add `similarity_score` to Applications
* Remove `Interviewing` from ApplicationStatus enum
* Enable pg_trgm extension in database.py
* Update init_db.py with test companies
* Run DB reset

### Phase 2: Self-Building Discovery + CORS
* Implement pg_trgm fuzzy search queries
* Add dynamic threshold logic
* Implement exclusion prompting in search API calls
* Save discovered companies to DB
* Add CORS middleware

### Phase 3: Hybrid Extraction with Upsert
* Refactor extraction service with upsert logic
* Implement ATS fast path with HTTPX
* Keep Crawl4AI fallback
* Generate job embeddings on insert
* Create embeddings service

### Phase 4: Vector Matching
* Integrate OpenAI embeddings
* Implement cosine similarity search
* Build `/jobs/match` endpoint
* Return ranked list (no text generation)

### Phase 5: JIT Application Generation
* Rename `/draft` to `/prepare`
* Move cover letter generation to JIT trigger
* Implement PII stripping
* Dynamic resume tailoring
* EU AI Act logging
* Store similarity_score on application creation

### Phase 6: Combined Pipeline + Testing
* Create `/pipeline/search-and-match` endpoint
* Update all tests for new schema
* E2E test: search → match → prepare → approve
* Performance optimization

---

## 10. Files to Create/Modify/Delete

### Create
| File | Purpose |
|------|---------|
| `src/services/embeddings.py` | OpenAI embedding generation |
| `src/services/vector_match.py` | Cosine similarity logic |
| `src/api/routers/pipeline.py` | Combined `/search-and-match` endpoint |

### Modify
| File | Changes |
|------|---------|
| `src/models.py` | Add Company, CompanySizeEnum; update Job with FK + new columns; add embedding fields to Job/Resume; add similarity_score to Application; remove Interviewing status |
| `src/database.py` | Enable pg_trgm extension on startup |
| `src/services/job_discovery.py` | Self-building logic, exclusion prompting, dynamic thresholds |
| `src/services/hybrid_extraction.py` | Upsert logic, embedding generation on insert |
| `src/api/routers/jobs.py` | New endpoints: `/search`, `/extract`, `/match` |
| `src/api/routers/applications.py` | Rename `/draft` → `/prepare`, add JIT logic, store similarity_score |
| `src/main.py` | Add CORS middleware, include pipeline router |
| `requirements.txt` | Add `openai` |
| `init_db.py` | Add test companies |

### Delete
| File | Reason |
|------|--------|
| `test_zai.py` | Debug file |
| `test_zai2.py` | Debug file |
| `poc_core_engine.py` | PoC complete |

### Update Tests
| File | Changes |
|------|---------|
| `tests/test_models.py` | Test new Company model, updated Job fields |
| `tests/test_api/test_jobs.py` | Test new endpoints |
| `tests/test_api/test_applications.py` | Test JIT pattern, similarity_score |
| `tests/test_services/test_job_discovery.py` | Test self-building logic |
| `tests/conftest.py` | Add fixtures for Company model |

---

## 11. Security Considerations

### Already Covered
| Threat | Protection |
|--------|------------|
| SQL Injection | SQLAlchemy parameterized queries |
| Input Validation | Pydantic strict typing |
| Rate Limiting | `check_rate_limit` dependency |
| Auth | JWT via `verify_jwt` |

### Extendable Later (via DI Pattern)
| Threat | Solution |
|--------|----------|
| Brute Force | Account lockout middleware |
| DDoS | Cloudflare / reverse proxy rate limiting |
| PII in Logs | Log sanitization filter |

---

## 12. Async Migration Path (Future)

When scaling requires async:

```python
# 1. Change DB driver: psycopg2-binary → asyncpg
# 2. Use AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# 3. Add await to queries
result = await db.execute(query)

# 4. HTTPX already supports async
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

The dependency injection pattern ensures no structural changes needed.
