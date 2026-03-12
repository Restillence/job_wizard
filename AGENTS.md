# JobWiz Architecture & Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a robust, scalable, GDPR-compliant MVP for an AI-powered B2C Job Application Assistant.

**Architecture:** API-first, Synchronous-First/Scale-Later methodology.

**Tech Stack:** Python 3.12+ (in `jobwiz_env` conda env), FastAPI, SQLAlchemy 2.0, Pydantic 2.0, PostgreSQL, HTTPX, Crawl4AI, Pytest.

## 1. Build/Lint/Test Commands

**Environment Setup:**
```bash
conda activate jobwiz_env
```

**Testing:**
```bash
# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_api/test_applications.py -v

# Run a specific test function
pytest tests/test_api/test_applications.py::test_create_application_draft -v

# Run with coverage
pytest --cov=src tests/
```

**Linting & Formatting:**
```bash
# We use ruff for both linting and formatting (fastest 2026 standard)
ruff check .
ruff format .

# Type checking
mypy src/
```

## 2. Code Style & Guidelines

*   **Imports:** Grouped (Standard library, Third-party, Local). Managed by `ruff`.
*   **Formatting:** `ruff format` defaults (line length 88 or 100).
*   **Typing:** Strict type hinting required everywhere. Use `mypy` for validation.
*   **Naming Conventions:**
    *   Variables/Functions: `snake_case`
    *   Classes: `PascalCase`
    *   Constants: `UPPER_SNAKE_CASE`
*   **Error Handling:** Use FastAPI's `HTTPException` for API boundaries. Custom exception classes for domain logic. Never catch generic `Exception` without re-raising or logging extensively.
*   **Dependency Injection:** Extensively use FastAPI's `Depends` for database sessions, configuration, and external services to ensure testability.
*   **Synchronous First:** Do not use `asyncio` for standard I/O bound tasks initially unless required by the framework (FastAPI) or library (Crawl4AI). Avoid task queues (Celery/Redis) until MVP validation.

## 3. Database Schema & Storage

The database relies on PostgreSQL and SQLAlchemy 2.0.
**Multi-Tenancy (SaaS Readiness):** Every user-specific table (Resumes, Applications, Interview_Prep) MUST include a `user_id` as a Foreign Key linking back to the Users table.
**Stateless File Storage:** Resumes and generated Cover Letters must be saved locally (e.g., `uploads/`). The DB must only store relative file paths (strings). This Adapter Pattern ensures seamless future migration to AWS S3/Supabase.

### Users
*   `id`: UUID (Primary Key)
*   `email`: String (Unique, Indexed)
*   `hashed_password`: String
*   `created_at`: DateTime (UTC)
*   `zusatz_infos`: JSONB (For future B2B extensions, skills, preferences)

### Resumes
*   `id`: UUID (Primary Key)
*   `user_id`: UUID (Foreign Key -> Users.id)
*   `file_path`: String (Relative path, e.g., 'uploads/resumes/uuid.pdf')
*   `created_at`: DateTime (UTC)

### Jobs
*   `id`: UUID (Primary Key)
*   `source_url`: String (Unique)
*   `title`: String
*   `company`: String
*   `description`: Text
*   `extracted_requirements`: JSONB (Parsed via AI/Scraper)
*   `created_at`: DateTime (UTC)

### Applications
*   `id`: UUID (Primary Key)
*   `user_id`: UUID (Foreign Key -> Users.id)
*   `job_id`: UUID (Foreign Key -> Jobs.id)
*   `status`: Enum (`Drafted`, `Approved`, `Sent`, `Interviewing`, `Rejected`)
*   `ai_match_rationale`: Text (EU AI Act logging - why this user matches this job)
*   `cover_letter_file_path`: String (Relative path, e.g., 'uploads/cover_letters/uuid.pdf')
*   `created_at`: DateTime (UTC)
*   `updated_at`: DateTime (UTC)

### Interview_Prep
*   `id`: UUID (Primary Key)
*   `user_id`: UUID (Foreign Key -> Users.id)
*   `job_id`: UUID (Foreign Key -> Jobs.id)
*   `content`: Text
*   `created_at`: DateTime (UTC)

## 4. API Architecture & Core Features

*   **`POST /api/v1/resumes/upload`**: Uploads a PDF/Docx to local storage (S3-ready). Triggers the synchronous PII stripping pipeline before processing.
*   **`GET /api/v1/jobs/discover`**: **Agentic Research Module.** Takes a user query (e.g., "10 biggest finance companies in Frankfurt"), uses a Web Search API (Tavily/Brave), and feeds results to an LLM. The LLM extracts company names and career URLs, outputting a JSON array for the Scraper.
*   **`POST /api/v1/applications/draft`**: Generates a cover letter draft for a specific job and user profile, saved to local storage.
*   **`GET /api/v1/applications/{app_id}/draft`**: Fetches the AI-drafted cover letter file path for human review.
*   **`POST /api/v1/applications/{app_id}/approve`**: Human-in-the-loop trigger. Changes status to 'Approved' and queues for sending (synchronously in MVP).
*   **`GET /api/v1/applications/{app_id}/interview-prep`**: Generates a custom interview cheat sheet based on the job description and user's (stripped) profile.

## 5. Hybrid Extraction Pipeline

This pipeline operates synchronously in the MVP phase.

**Step 1: ATS Pattern Matching (Fast Path)**
1.  Receive Target URL (often provided by the Agentic Discovery Module).
2.  Regex/String match URL against known footprints (`personio.de`, `workday.com`, `index.php?ac=jobad`).
3.  If matched, route to specific fast-path parser using `httpx`.
4.  Extract JSON/API payload.
5.  Validate against Pydantic `JobSchema`.

**Step 2: Dynamic AI Fallback (Slow Path)**
1.  If URL is unknown, initialize `Crawl4AI` (synchronously awaited if async is forced by library).
2.  Navigate and extract raw HTML/Markdown text.
3.  Pass raw text to LLM structured output endpoint (e.g., OpenAI/Anthropic with function calling) asking for `JobSchema`.
4.  Validate resulting JSON against Pydantic `JobSchema`.

## 6. Phased Execution Plan (Component-Driven)

### Phase 1: Core Engine Proof of Concept (PoC)
*   **Goal:** Prove the Agentic Discovery and Hybrid Extraction work before building the app.
*   **Output:** A single, synchronous Python script that tests:
    1.  Agentic Discovery (Search API + LLM -> JSON Array of URLs).
    2.  Hybrid Extraction Engine (ATS Fast Path check + Crawl4AI fallback -> Pydantic `JobSchema`).

### Phase 2: DB, Storage & FastAPI Scaffolding
*   **Goal:** Scaffolding, DB connection (Multi-Tenant), stateless file storage setup, and basic health check.
*   **Output:** Working FastAPI server with SQLAlchemy models, alembic migrations, and the local `uploads/` directory structure.

### Phase 3: Resume Processing & Privacy
*   **Goal:** PII stripping and basic resume parsing.
*   **Output:** A service that takes text/PDF, uses NLP/LLM to identify Name/Email/Phone, replaces them with placeholders (`[REDACTED]`), and returns the sanitized profile.

### Phase 4: API Endpoint Integration
*   **Goal:** Wire the domain logic (Discovery, Extraction, Generation) to the REST endpoints.
*   **Output:** Functional endpoints for upload, discovery, draft generation, review, approval, and interview prep. E2E tests passing using SQLite/Test DB.

### Phase 5: Production Readiness & Scaling Strategy
*   **Goal:** Finalize MVP and plan for async.
*   **Output:** Logging setup (EU AI Act compliance), Dockerfile, and a technical design document for moving to Celery/Redis in v2.
