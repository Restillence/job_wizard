# JobWiz: AI-Powered B2C Job Application Assistant

JobWiz is a robust, scalable, GDPR-compliant MVP designed to automate and enhance the job application process for the European market. Built with an API-first, Synchronous-First/Scale-Later architecture.

## 🌟 Core Features

*   **Agentic Job Discovery:** Uses Web Search APIs and LLMs to dynamically discover relevant companies and career pages based on natural language queries (e.g., "Find AI engineering roles in Berlin").
*   **Hybrid Job Extraction:** 
    *   *Fast Path:* Identifies ATS footprints (Personio, Workday, Greenhouse) for rapid parsing.
    *   *Slow Path:* Employs dynamic AI fallbacks (`Crawl4AI` + LLM) to scrape unstructured career pages.
*   **GDPR-Compliant PII Stripping:** Automatically redacts sensitive Personal Identifiable Information (Names, Emails, Phone numbers) from uploaded resumes before any data is sent to external AI providers.
*   **AI Cover Letter Drafting:** Generates tailored cover letters by matching user resumes against extracted job requirements.
*   **EU AI Act Logging:** Transparently logs the "AI Match Rationale"—explaining exactly *why* the AI believes a candidate matches a specific job role.
*   **Human-in-the-Loop:** Applications are saved as "Drafts" requiring explicit user approval before proceeding.

## 🏗️ Technology Stack

*   **Language:** Python 3.12+
*   **Framework:** FastAPI
*   **Database ORM:** SQLAlchemy 2.0 (Strict Typing with `Mapped`)
*   **Database:** SQLite (MVP/Testing) -> PostgreSQL (Production)
*   **Data Validation:** Pydantic 2.0
*   **LLM Integration:** LiteLLM (Currently configured for Z.ai GLM-5 via OpenAI-compatible endpoints)
*   **Web Scraping:** Crawl4AI (Async Playwright), HTTPX
*   **Testing:** Pytest (Unit, Integration, and live E2E pipelines)

## 🚀 Getting Started (Local Development)

### 1. Environment Setup

It is highly recommended to use Conda for environment management.

```bash
# Create and activate the environment
conda create -n jobwiz_env python=3.12
conda activate jobwiz_env

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (Required for Crawl4AI)
python -m playwright install --with-deps chromium
```

### 2. Configuration

Create a `.env` file in the root directory (or rely on the defaults in `src/config.py`). You will need a valid Z.ai API key for the AI features to function.

```env
ZAI_API_KEY="your_zai_api_key_here"
ZAI_API_BASE="https://api.z.ai/api/coding/paas/v4"
RUN_E2E_TESTS=False
```

### 3. Running the Server

Start the FastAPI application with Uvicorn:

```bash
uvicorn src.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### 4. API Documentation (Swagger UI)

FastAPI automatically generates interactive API documentation. Once the server is running, navigate to:

👉 **http://127.0.0.1:8000/docs**

Here you can test endpoints like `/api/v1/jobs/discover` or `/api/v1/resumes/upload` directly from your browser.

## 🧪 Testing Strategy

JobWiz employs a dual-testing strategy to balance speed and real-world reliability:

### Unit & Integration Tests (Fast, $0 Cost)
These tests use in-memory SQLite databases and heavily mock external network calls (LLMs and Search APIs). They run in milliseconds and should be executed frequently.

```bash
# Run all standard tests
pytest tests/ -v -k "not e2e"
```

### End-to-End (E2E) Live Tests (Slow, Uses Real API Credits)
These tests hit the live Z.ai API and perform real web searches to validate the extraction and generation logic against real-world unpredictability. **These are disabled by default to prevent accidental API charges.**

```bash
# Enable the safety flag and run E2E tests
set RUN_E2E_TESTS=1   # Windows CMD
export RUN_E2E_TESTS=1 # Mac/Linux/Git Bash

pytest tests/e2e/ -v -s
```

## 📂 Project Structure

```text
job_wizard/
├── src/
│   ├── api/
│   │   ├── routers/       # FastAPI endpoints (jobs, resumes, applications)
│   │   └── deps.py        # Dependency Injection (Auth, Rate Limiting)
│   ├── services/          # Core Business Logic (PII Stripping, LLM calls, Scrapers)
│   ├── config.py          # Pydantic Settings
│   ├── database.py        # SQLAlchemy Engine & Session
│   ├── main.py            # FastAPI App initialization
│   └── models.py          # SQLAlchemy Database Models (Users, Jobs, Applications)
├── tests/
│   ├── e2e/               # Live pipeline tests (Real LLM/Web calls)
│   ├── test_api/          # Endpoint integration tests (Mocked)
│   ├── test_services/     # Service unit tests (Mocked)
│   └── conftest.py        # Pytest fixtures and DB overrides
├── uploads/               # Local stateless file storage (Adapter pattern for future S3)
├── Dockerfile             # Production containerization
├── requirements.txt       # Project dependencies
└── technical_design_v2.md # Future scaling strategy (Celery + Redis)
```

## 🔐 Security & Quotas

*   **Multi-Tenancy:** All user-specific data is strictly isolated via Foreign Keys.
*   **Rate Limiting:** Built-in credit tracking (`credits_used` vs `credits_limit`) implemented via FastAPI dependencies.
*   **Superuser Bypass:** Accounts flagged with `is_superuser=True` bypass all quota restrictions for unlimited access.
