# JobWiz — AI Assistant Instructions

> You are the AI coding assistant for **JobWiz**, a GDPR-compliant, DACH-first AI-powered B2C job application assistant. Every decision you make must consider GDPR, the EU AI Act, and DACH-region specifics (Germany, Austria, Switzerland) as first-class constraints.

---

## Who You Are

You build features for a **B2C tool that helps job applicants** — not employers. Users are individual job seekers in Germany, Austria, and Switzerland. Their data is sacred. PII stripping is mandatory. Logging is auditable. The EU AI Act requires transparency in every LLM interaction.

You write **Python** that runs on Windows in a Conda environment. You favour **simple, synchronous code** over clever async patterns. You ship MVP-quality first, production-hardened later.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | **Python 3.12** | Conda env: `jobwiz_env` |
| API | **FastAPI** | REST, API-first |
| ORM | **SQLAlchemy 2.0** + **Pydantic 2.0** | Strict typing |
| Database | **SQLite** (dev) → **PostgreSQL** (prod, pg_trgm) | Migration planned |
| LLM | **LiteLLM → GLM-5.1** via **Z.AI API** (OpenAI-compatible) | Model prefix: `openai/glm-5.1` |
| Embeddings | **Gemini text-embedding-004** (3072-dim) | ⚠️ Deprecated Jan 14, 2026 → migrate to `gemini-embedding-001` |
| Crawling | **Crawl4AI v0.8.0** + **HTTPX** | Hybrid extraction |
| Testing | **Pytest** (~291 tests, Phases 1–8 complete) | `--cov=src` |
| Linting | **ruff** (line 88), **mypy** (strict) | |
| Queue | **Celery + Redis** (V2, post-MVP) | NOT current scope |

### Free Data Sources
- **Arbeitsagentur API** (OAuth2, official German job board)
- **Arbeitnow** (aggregated listings API)
- **LLM-driven company discovery** (GLM-5.1 suggests companies by criteria)
- **Crawl4AI** for enrichment of career pages

### Environment Variables
- `ZAI_API_KEY` — Z.AI API key (⚠️ currently 401, needs regeneration)
- `ZAI_API_BASE` — Z.AI API base URL
- `RUN_E2E_TESTS=False` — gate for end-to-end tests

---

## Build / Lint / Test Commands

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

## Code Style

- **Imports:** Grouped (stdlib → third-party → local). Managed by `ruff`.
- **Formatting:** `ruff format` defaults (line length 88).
- **Typing:** Strict type hints required. `mypy` for validation.
- **Naming:** `snake_case` (vars/funcs), `PascalCase` (classes), `UPPER_SNAKE_CASE` (constants).
- **Error Handling:** `HTTPException` at API boundaries. Custom exceptions for domain logic.
- **Dependency Injection:** `Depends` for DB sessions, config, and external services.
- **Security:** All protected endpoints → `Depends(verify_jwt)` + `Depends(check_rate_limit)`.
- **Sync First:** No `asyncio` unless required by framework/library. No Celery/Redis until MVP validation.

---

## ⛔ Lessons Learned — DO NOT Repeat These Mistakes

> **Maintenance rule:** Every time a bug is found and fixed, add an entry here.
> Format: **ID → What happened → Root cause → The rule.**

### LLM-001: GLM-5.1 reasoning mode returns empty `message.content`
- **What:** `message.content` was `""` while actual text sat in `reasoning_content`.
- **Root cause:** GLM-5.1 API bug — not caught because code assumed content is always populated.
- **Rule:** ALWAYS use `call_llm` / `acall_llm` from `src/services/llm_utils.py`. NEVER call `litellm.completion()` directly. The `_extract_content()` fallback chain handles this.

### LLM-002: Stale litellm import left after refactor
- **What:** `from litellm import completion, acompletion` was still present in `job_discovery.py` after migrating to `call_llm` helpers.
- **Root cause:** Incomplete refactor — helpers were added but old imports not cleaned up.
- **Rule:** After any refactor, grep for old patterns: `rg "from litellm import" src/` must return zero hits outside `llm_utils.py`.

### LLM-003: Free model alternatives exist
- **What:** GLM-5.1 is Coding Plan only, but Z.AI offers free models.
- **Rule:** If GLM-5.1 is down/expensive, switch to: **GLM-4.7-Flash** (free), **GLM-4.5-Flash 128K** (free), **GLM-4.7-FlashX** ($0.07/$0.40 per 1M).

### EMB-001: Gemini text-embedding-004 deprecated
- **What:** API will stop working Jan 14, 2026.
- **Rule:** Use `gemini-embedding-001`. Verify dimensions before migration — may differ from 3072.

### TEST-001: Mocking call_llm but service still imports litellm directly
- **What:** Tests patched `call_llm` but the service file had a direct `litellm` import that ran at import time.
- **Rule:** Tests must match the actual import path used by the service. Verify with `rg "from litellm" src/`.

### CRAWL-001: Major job boards block Crawl4AI
- **What:** Stepstone, Indeed, Glassdoor block via Akamai/Cloudflare WAF. Crawl4AI stealth mode cannot bypass.
- **Rule:** These domains are in the aggregator exclusion list. DO NOT attempt to scrape them. Use Arbeitsagentur API and Arbeitnow instead.

### EXTRACT-001: Slow-path has ~70% false positive rate
- **What:** Heuristic extractor misidentifies navigation/footer links as job listings.
- **Rule:** ATS fast-path is preferred where available. Slow-path results need LLM validation before upsert.

### LLM-004: GLM-5.1 reasoning mode truncates extraction output
- **What:** `max_tokens=4096` was split between `reasoning_content` + `content`, leaving only ~1800 chars for actual JSON extraction from job pages.
- **Root cause:** Reasoning mode is inherent to GLM-5.1 — cannot be disabled.
- **Rule:** Use `model="openai/glm-4.7-flash"` (free, no reasoning) for all extraction tasks. Full token budget goes to content.

### ASYNC-001: Sync call_llm inside async def blocks event loop
- **What:** `scrape_single_job`, `extract_from_raw_text`, `_crawl4ai_fallback` were `async` methods calling sync `call_llm`, blocking the FastAPI event loop.
- **Root cause:** Missing conversion during initial implementation.
- **Rule:** All `async` methods must use `acall_llm`, not `call_llm`.

### ENCODING-001: Crawl4AI corrupts German umlauts on Windows
- **What:** Crawl4AI HTML→markdown conversion produces corrupted umlauts (e.g. `ü` → garbled bytes) on Windows cp1252 consoles.
- **Root cause:** `sys.stdout.reconfigure` only fixes console output, not the crawler's internal encoding.
- **Rule:** Always run `_sanitize_encoding()` on `result.markdown` before processing. Implemented in `crawl_utils.py:clean_markdown()`.

### DRY-001: Duplicate crawl configs and cleaning functions
- **What:** `_clean_markdown()`, `CrawlerRunConfig`, noise patterns were duplicated between `hybrid_extraction.py` and `job_extraction.py` with different defaults (8000 vs 12000 chars).
- **Root cause:** Two files evolved independently.
- **Rule:** All crawl-related shared code lives in `src/services/crawl_utils.py`. Single `JOB_CRAWL_CONFIG` instance, single `clean_markdown()` function.

---

## Anti-Cheat Rules

These are **non-negotiable**. Violating them breaks test integrity and hides real bugs.

1. **NO Mocking External Services in Integration Tests.** Mock at the HTTP/SDK level — never mock the service layer itself unless testing service-layer logic in isolation.
2. **NO Hardcoded Fallbacks.** If a service fails, it must **fail loudly** — return an error, not silently fall back to a hardcoded value.
3. **FAIL LOUDLY.** Every error path must produce a visible, loggable error. No bare `except: pass`.
4. **RADICAL TRANSPARENCY.** Every LLM prompt and response must be logged (prompt hash, token counts, model name, timestamps). Required by §4.6 EU AI Act Logging.
5. **FIX SERVICE LOGIC, NOT TESTS.** If a test fails, the fix is in the service code — never adjust a test to pass around a service bug. Tests are the contract.

---

## LLM Helpers — `src/services/llm_utils.py`

All 8 service files use these centralized helpers:

```python
from src.services.llm_utils import call_llm, acall_llm

# Sync
result: str = call_llm(prompt, model="openai/glm-5.1", max_tokens=4096, timeout=120)

# Async
result: str = await acall_llm(prompt, model="openai/glm-5.1", max_tokens=4096, timeout=120)
```

- Call LiteLLM `completion()` / `acompletion()`
- Run `_extract_content()` fallback: `message.content` → `reasoning_content` → `choices[0].text` → raise
- Return **plain string** (not LiteLLM response object)
- Defaults: `model="openai/glm-5.1"`, `max_tokens=4096`, `timeout=120`

**Deployed across:** `company_discovery.py`, `job_discovery.py`, `job_extraction.py`, `hybrid_extraction.py`, `cv_generator.py`, `cv_parser.py`, `pii_stripping.py`

**NEVER** call `litellm.completion()` directly outside `llm_utils.py`.

### Model Selection Strategy

| Task | Model | Why |
|---|---|---|
| Extraction (scrape/raw_text → JSON) | `openai/glm-4.7-flash` | Free, no reasoning mode, full token budget for content |
| Matching, cover letter, CV tailoring | `openai/glm-5.1` (default) | Reasoning improves quality for complex generation |
| Embeddings | `gemini/gemini-embedding-001` | 3072-dim, separate from LLM calls |

Extraction calls pass `model="openai/glm-4.7-flash"` explicitly. All other calls use the default `openai/glm-5.1`.

### Shared Crawl Utils — `src/services/crawl_utils.py`

Centralized crawling config and markdown cleaning used by both `hybrid_extraction.py` and `job_extraction.py`:

- `JOB_CRAWL_CONFIG` — single `CrawlerRunConfig` instance (excluded tags, selectors, only_text)
- `clean_markdown(md, max_chars=12000)` — head/tail trimming, noise pattern removal, encoding sanitization
- `_sanitize_encoding(text)` — encode/decode safety pass for Crawl4AI output (fixes umlaut corruption on Windows)

---

## Database Schema

**CompanySize Enum:** `startup` | `hidden_champion` | `enterprise`

| Table | Key Columns | Notes |
|---|---|---|
| **Users** | `id` (UUID PK), `email` (unique, indexed), `hashed_password`, `zusatz_infos` (JSONB — **critical** for vector matching), `subscription_tier` (default 'free'), `credits_used`/`credits_limit` (default 0/10), `is_superuser` | |
| **Companies** | `id` (UUID PK), `name` (indexed), `city`, `industry`, `company_size` (enum), `url` (career page, unique), `url_verified` (HEAD vs LLM-predicted) | |
| **UserSearches** | `id` (UUID PK), `user_id` (FK→Users), `cities`/`industries`/`keywords` (JSON), `created_at` | Auto-deleted after 5 per user |
| **Jobs** | `id` (UUID PK), `company_id` (FK→Companies), `source_url` (unique, indexed), `title`, `description`, `extracted_requirements` (JSONB), `embedding` (JSON, 3072 floats), `is_active` (soft-delete), `first_seen_at`, `last_seen_at` | |
| **Resumes** | `id` (UUID PK), `user_id` (FK→Users), `file_path`, `parsed_data` (JSON), `embedding` (JSON) | |
| **CoverLetters** | `id` (UUID PK), `user_id` (FK→Users), `job_id` (FK→Jobs), `content`, `version` (default 1), `status` (draft/final/sent), `revision_info` (JSONB: prompt, revision, diff) | |
| **Applications** | `id` (UUID PK), `user_id`, `job_id`, `status`, `cover_letter_id`, `ai_match_rationale` | Interface only — legal gate before full implementation |

---

## API Endpoint Contracts

### `POST /api/v1/companies/search`
Search companies with fuzzy matching. Triggers self-building discovery if results below threshold.

**Params:** `cities` (list, OR), `industries` (list, OR), `keywords` (list, fuzzy), `company_size` (enum).

**Logic:**
1. Query Companies with pg_trgm fuzzy search.
2. Threshold: broad (no filters) → 50 results; specific (any filter) → 5 results.
3. Below threshold → search API fallback → two-step extraction (LLM extracts company names → predicts career URLs).
4. **Aggregator Exclusion:** Always exclude `linkedin.com`, `indeed.com`, `glassdoor.com`, `stepstone.de`, `xing.com`.
5. **Exclusion Prompting:** Exclude existing DB company names from search queries.
6. HEAD validate predicted URLs → `url_verified = True/False`.
7. Save new companies, return combined.

**Response:** `{ "companies": [...], "total_found": N, "newly_added": N, "source": "local" | "api_fallback" }`

### `GET /api/v1/companies/{company_id}/resolve-url`
If `url_verified = True` → return URL. If `False` → search for actual career page, update `url`, set `url_verified = True`, return.

### `POST /api/v1/jobs/extract`
**Body:** `{ "company_ids": ["uuid1", "uuid2"] }`. Run Hybrid Extraction per company. Upsert: existing (by `source_url`) → update `last_seen_at`, `is_active = True`; new → insert + generate embedding.

**Response:** `{ "jobs": [...], "total_extracted": N, "newly_added": N, "updated": N }`

### `POST /api/v1/jobs/match`
**Body:** `{ "user_id": "uuid", "company_ids": ["uuid1"], "top_k": 20 }`. Resume embedding vs job embeddings, cosine similarity, ranked list. **DO NOT generate cover letters** — JIT only.

**Response:** `{ "matched_jobs": [{ "job_id", "title", "company_name", "similarity_score", "is_new_match" }], "total_matches": N }`

### `POST /api/v1/applications/prepare`
**JIT Trigger** — only on user click "Prepare Application". Strip PII → tailor resume → generate cover letter → log AI match rationale (EU AI Act) → save as `Drafted`.

**Response:** `{ "application_id": "uuid", "cover_letter_path": "...", "ai_match_rationale": "...", "status": "Drafted" }`

### `POST /api/v1/applications/{app_id}/approve`
Human-in-the-loop. Status → `Approved`.

### `POST /api/v1/resumes/upload`
PDF/Docx → strip PII → generate embedding → save.

### `POST /api/v1/pipeline/search-and-match`
One-shot discovery + matching. **Body:** `{ "cities", "industries", "keywords", "company_size", "user_id", "top_k": 20 }`. Flow: `/companies/search` → `/jobs/extract` → `/jobs/match` → save search to history (max 5).

---

## Self-Building Discovery Logic

```
THRESHOLDS:
  Broad query (no filters):    50 companies
  Specific query (any filter):  5 companies

TWO-STEP EXTRACTION (on search API fallback):
  Step 1: LLM extracts company names from job listings
  Step 2: LLM predicts career page URLs for each company
  Step 3: HEAD validate predicted URLs → url_verified=True/False
  Lazy Resolution: Real search only when user clicks unverified company

AGGREGATOR EXCLUSION (always):
  linkedin.com, indeed.com, glassdoor.com, stepstone.de, xing.com

EXCLUSION PROMPTING:
  "Find 20 companies matching [query], but EXCLUDE:
   [Company A, Company B, ...existing DB names...]"

CITY-PRIMARY QUERY STRATEGY:
  - One query per city (max 5 cities)
  - Combine industries/keywords into each query
  - Dedupe across queries
  - Append aggregator exclusions to every query
```

---

## Hybrid Extraction Engine

### ATS Fast Path (HTTPX, preferred)
| ATS | URL Pattern | Method |
|-----|-------------|--------|
| Personio | `personio.de` | Hidden JSON API |
| Workday | `workday.com` | JSON endpoint |
| Greenhouse | `greenhouse.io` | JSON API |

### Slow Path (Crawl4AI + LLM, fallback)
1. Navigate to career page → extract markdown
2. Pass to LLM with `JobSchema` structured output
3. Validate with Pydantic
4. ⚠️ ~70% false positive rate — needs LLM validation before upsert

---

## Vector RAG Pipeline

**Model:** `gemini-text-embedding-004` (3072-dim) → migrate to `gemini-embedding-001`.

**Pre-compute:** Resume upload → `Resume.embedding`; Job extraction → `Job.embedding`.

**Query Flow:** User profile (CV + `zusatz_infos`) → embed (cached on Resume) → cosine similarity against jobs → top-k ranked.

---

## Security

| Threat | Protection |
|--------|------------|
| SQL Injection | SQLAlchemy parameterized queries |
| Input Validation | Pydantic strict typing |
| Rate Limiting | `check_rate_limit` dependency |
| Auth | JWT via `verify_jwt` |
| PII Exposure | Names→FIRST(), addresses→YOOZI(), emails→LATTE(), phone→URGENT() |

---

## Current Status

**Phases 1–8 complete.** ~291 tests. Ready for integration testing and bug fixes.

### Blocking
- **Z.AI API key 401** — regenerate at https://z.ai/. Free alternatives: GLM-4.7-Flash, GLM-4.5-Flash 128K.
- **Gemini text-embedding-004 deprecated** — migrate to `gemini-embedding-001` before Jan 14, 2026.

### Pending Test Fixes
- `job_discovery.py` stale `from litellm import` — needs removal
- `TestingSessionLocal` export from `conftest.py`
- `httpx.AsyncClient` patching adjustment
- 5 test files in `tests/test_services/` updated but **not yet run**

### Open Bugs
- 4 bugs from live DACH portal testing remain open
- ATS fast-path covers only ~25% of sites
- Switzerland (Jobs.ch, Jobup.ch) weakest coverage
