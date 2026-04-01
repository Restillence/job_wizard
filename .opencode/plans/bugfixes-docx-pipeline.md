# Implementation Plan: Bug Fixes + DOCX CV/Cover Letter Pipeline

## Task 1: Fix 3 Pre-existing Bugs

### Bug 1: UnicodeDecodeError in resume upload
**File:** `src/api/routers/resumes.py:36`
**Problem:** `content.decode("utf-8")` crashes on binary files (PDF/DOCX)
**Fix:** Add file type detection. For now, accept `.txt` files and return 400 for unsupported types. (Proper PDF/DOCX handling in Task 3.)

### Bug 2: Unawaited coroutine in reuse_search
**File:** `src/api/routers/users.py:111`
**Problem:** `discovery_service.search_companies()` is `async def` but called without `await`, returning a coroutine object instead of `CompanySearchResult`
**Fix:** Add `await` before the call. The router function is already `async def`.

### Bug 3: _build_search_query only uses first city
**File:** `src/services/job_discovery.py:247`
**Problem:** `city = cities[0] if cities else ""` — only uses first city, ignoring "Munich" in `["Berlin", "Munich"]`
**Fix:** Include all cities in the query string, e.g., `"Berlin" "Munich"` instead of just `"Berlin"`

## Task 2: PDF/DOCX Resume Upload + E2E Vector Match

### 2a: Install dependencies
```bash
pip install pymupdf python-docx
```

### 2b: Update resume upload endpoint
**File:** `src/api/routers/resumes.py`
- Accept `.txt`, `.pdf`, `.docx` files
- Extract text using appropriate library:
  - `.txt`: direct decode
  - `.pdf`: `pymupdf` (fitz)
  - `.docx`: `python-docx`
- Store both original file and extracted text
- Add `original_file_path` field to Resume model (or use naming convention)

### 2c: Verify E2E flow
- Upload real PDF CV → get embedding
- Hit `/jobs/search-boards` → populate jobs with embeddings
- Hit `/jobs/match` → get ranked results with similarity scores

## Task 3: Auto-generated Tailored CV + Cover Letter (DOCX)

### 3a: CV Structure Extraction
**New file:** `src/services/cv_parser.py`
- Parse extracted text into structured sections (summary, experience, education, skills)
- Use LLM to identify sections and content blocks

### 3b: CV Tailoring Service
**New file:** `src/services/cv_generator.py`
- LLM receives: structured CV + job description + requirements
- LLM returns: tailored content (JSON with sections)
- Key behaviors:
  - Reorder skills to match job requirements
  - Emphasize relevant experience
  - Adjust professional summary to target role
  - Keep truthful — only reorder/emphasize, don't fabricate

### 3c: DOCX Template Renderer
**New file:** `src/services/docx_renderer.py`
- Professional DOCX template with consistent formatting
- Renders tailored CV content into the template
- Renders cover letter into separate DOCX template
- Uses `python-docx`

### 3d: Update `/applications/prepare` endpoint
**File:** `src/api/routers/applications.py`
- New response fields: `cv_path`, `cover_letter_path` (both DOCX)
- Replace plain text cover letter with DOCX output
- Add tailored CV generation

## Task 4: Tests

### Update existing tests
- `tests/test_api/test_resumes.py`: Test PDF/DOCX upload, test unsupported format rejection
- `tests/test_api/test_applications.py`: Test DOCX output, mock CV generator
- `tests/test_api/test_users.py`: Verify reuse_search fix

### New tests
- `tests/test_services/test_cv_generator.py`: CV tailoring logic
- `tests/test_services/test_cv_parser.py`: Section extraction

## Execution Order
1. Task 1 (bug fixes) — independent, quick
2. Task 2 (PDF/DOCX upload) — depends on Task 1 bug fix
3. Task 3 (DOCX generation) — depends on Task 2
4. Task 4 (tests) — runs throughout

## Dependencies to Install
```
pymupdf
python-docx
```
