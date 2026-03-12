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

## 3. Database Schema

The database relies on PostgreSQL and SQLAlchemy 2.0.

### Users
*   `id`: UUID (Primary Key)
*   `email`: String (Unique, Indexed)
*   `hashed_password`: String
*   `created_at`: DateTime (UTC)
*   `zusatz_infos`: JSONB (For future B2B extensions, skills, preferences)

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
*   `cover_letter_draft`: Text
*   `created_at`: DateTime (UTC)
*   `updated_at`: DateTime (UTC)

## 4. API Architecture & Core Features

*   **`POST /api/v1/resumes/upload`**: Uploads a PDF/Docx. Triggers the synchronous PII stripping pipeline before storing/processing.
*   **`POST /api/v1/applications/draft`**: Generates a cover letter draft for a specific job and user profile.
*   **`GET /api/v1/applications/{app_id}/draft`**: Fetches the AI-drafted cover letter for human review.
*   **`POST /api/v1/applications/{app_id}/approve`**: Human-in-the-loop trigger. Changes status to 'Approved' and queues for sending (synchronously in MVP).
*   **`GET /api/v1/applications/{app_id}/interview-prep`**: Generates a custom interview cheat sheet based on the job description and user's (stripped) profile.

## 5. Hybrid Extraction Pipeline

This pipeline operates synchronously in the MVP phase.

**Step 1: ATS Pattern Matching (Fast Path)**
1.  Receive Target URL.
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

### Phase 1: DB & FastAPI Setup
*   **Goal:** Scaffolding, DB connection, and basic health check.
*   **Output:** Working FastAPI server with SQLAlchemy models for User, Job, Application and alembic migrations.

### Phase 2: Hybrid Extraction Engine
*   **Goal:** Build the synchronous URL scraping logic.
*   **Output:** A standalone Python service class `JobExtractor` that implements Step 1 (Requests) and Step 2 (Crawl4AI) returning a validated Pydantic model.

### Phase 3: Resume Processing & Privacy
*   **Goal:** PII stripping and basic resume parsing.
*   **Output:** A service that takes text/PDF, uses NLP/LLM to identify Name/Email/Phone, replaces them with placeholders (`[REDACTED]`), and returns the sanitized profile.

### Phase 4: API Endpoint Integration
*   **Goal:** Wire the domain logic to the REST endpoints.
*   **Output:** Functional endpoints for upload, draft generation, review, approval, and interview prep. E2E tests passing using SQLite/Test DB.

### Phase 5: Production Readiness & Scaling Strategy
*   **Goal:** Finalize MVP and plan for async.
*   **Output:** Logging setup (EU AI Act compliance), Dockerfile, and a technical design document for moving to Celery/Redis in v2.
