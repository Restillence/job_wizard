# JobWiz V2: Asynchronous Scaling Strategy (Celery + Redis)

## Current MVP State (V1)
In the MVP (Phase 1-5), JobWiz utilizes a **Synchronous-First** architecture.
- When a user uploads a resume, the PII stripping blocks the HTTP response until the LLM completes.
- When drafting a cover letter, the FastAPI process waits on the LLM generation.
- The `Crawl4AI` crawler utilizes async locally within the endpoint, but effectively blocks until complete.

This works perfectly for PoC/MVP to validate the value proposition, but it will fail at scale (e.g., 50+ concurrent users drafting cover letters simultaneously), as worker threads will be exhausted.

## V2 Architecture Proposal

To scale the application, we must decouple the slow, I/O-bound LLM and Scraping tasks from the FastAPI request/response cycle.

### Core Technologies
*   **Message Broker:** Redis (In-memory, extremely fast, also handles caching).
*   **Task Queue / Workers:** Celery (Industry standard for Python async task management).

### High-Level Workflow (V2)

1.  **Request Initiation:** The user requests a cover letter via `POST /api/v2/applications/draft`.
2.  **Task Queuing:** Instead of generating the letter, FastAPI enqueues a `generate_cover_letter_task` to Redis and creates an `Application` DB record with `status='Processing'`.
3.  **Immediate Response:** FastAPI instantly returns a `202 Accepted` with the `application_id`.
4.  **Background Processing:** A Celery Worker picks up the task from Redis, executes the `HybridExtractionService` (if needed) and `CoverLetterService` (LLM call).
5.  **State Update:** The Celery worker saves the generated file to disk/S3 and updates the `Application` DB status to `Drafted`.
6.  **Client Notification (Optional):** The frontend can either:
    - **Poll:** `GET /api/v2/applications/{id}/status` every 3 seconds.
    - **WebSockets/SSE:** Receive a push notification when processing is complete.

### EU AI Act Compliance Refinement
In V2, logging AI Match Rationales (`ai_match_rationale`) will continue, but we will offload this logging to an ELK stack or a dedicated audit database via Celery beat to ensure the main transactional PostgreSQL database isn't burdened by massive text blobs over time.

### Statelessness & Storage (S3)
Since Celery workers might run on different physical machines/containers than the FastAPI server, the local `uploads/` directory must be replaced. 
All files (Resumes, Cover Letters) MUST be uploaded directly to AWS S3 (or a compatible service like MinIO/Supabase Storage) via presigned URLs. The database will store the S3 URI instead of the relative path.

## Migration Steps for V2
1.  Setup Redis container in `docker-compose.yml`.
2.  Install `celery` and `redis` Python packages.
3.  Create `src/worker.py` to define the Celery app instance.
4.  Move functions from `src/services/` into Celery `@task` decorators.
5.  Migrate local `os.path` file management to `boto3` for S3 integration.

## Frontend UX Notes (Job Discovery)
*When building the B2C frontend, the Job Discovery search bar needs specific UX handling to ensure high-quality LLM extraction:*

1. **Placeholder Text:** Use proactive placeholders like `e.g., top AI startups hiring in Berlin 2026`.
2. **Helper Tooltips/Chips:** Provide a 💡 tooltip or clickable suggestion chips under the search bar that teach users to bypass job boards. 
   * Example chips: `site:careers.*.com`, `-linkedin -stepstone`, `intitle:careers`.
3. **Empty States:** If the LLM returns an empty array `[]` (because the search snippets lacked explicit company names), the UI should clearly tell the user: *"We couldn't extract specific companies from these results. Try adding 'careers page' or excluding job boards like '-linkedin'."*
