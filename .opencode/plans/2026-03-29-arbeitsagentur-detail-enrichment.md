# Arbeitsagentur Detail Enrichment + Embeddings Pipeline

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fetch full job descriptions from Arbeitsagentur detail pages, generate embeddings, and make vector matching work end-to-end.

**Architecture:** After search API returns thin job data, enrich each job by fetching its detail page (simple HTTPX, extract embedded JSON from `<script>` tags). Generate Gemini embeddings from the enriched descriptions.

**Tech Stack:** HTTPX, regex JSON extraction, LiteLLM Gemini embeddings, SQLAlchemy

---

### Task 1: Add `fetch_detail()` to `ArbeitsagenturSource`

**Files:**
- Modify: `src/services/job_sources/arbeitsagentur.py`
- Create: `tests/test_services/test_arbeitsagentur_detail.py`

**What:** Add a method that fetches `https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}`, extracts the embedded `jobdetail` JSON from `<script>` tags, and returns a dict with `stellenangebotsBeschreibung`, `firma`, `stellenlokationen`, `arbeitszeitVollzeit`, `verguetungsangabe`, etc.

Key extraction logic:
```python
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

def fetch_detail(self, refnr: str) -> Optional[Dict[str, Any]]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html',
        'Accept-Language': 'de-DE,de;q=0.9',
    }
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        r = client.get(self.DETAIL_URL.format(refnr=refnr), headers=headers)
        if r.status_code != 200:
            return None
        return self._extract_jobdetail_json(r.text)

def _extract_jobdetail_json(self, html: str) -> Optional[Dict[str, Any]]:
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        if 'jobdetail' not in script:
            continue
        try:
            start = script.index('{')
            end = script.rindex('}') + 1
            data = json.loads(script[start:end])
            if 'jobdetail' in data:
                return data['jobdetail']
        except (ValueError, json.JSONDecodeError):
            continue
    return None
```

**Tests:**
- `test_fetch_detail_extracts_description` — mock HTTPX response with real HTML snippet containing embedded JSON, verify description extracted
- `test_fetch_detail_returns_none_on_404` — verify graceful failure on non-200 status
- `test_extract_jobdetail_json_parses_embedded_json` — unit test with crafted HTML string
- `test_fetch_detail_no_jobdetail_key` — script exists but no `jobdetail` key returns None

---

### Task 2: Add `enrich_jobs()` batch method

**Files:**
- Modify: `src/services/job_sources/arbeitsagentur.py`

**What:** Add `enrich_jobs(jobs: List[NormalizedJob]) -> List[NormalizedJob]` that calls `fetch_detail()` for each job, backfills `description` and other fields onto the `NormalizedJob` objects. Rate-limited with `time.sleep(0.2)` between requests.

```python
import time

def enrich_jobs(self, jobs: List[NormalizedJob]) -> List[NormalizedJob]:
    for job in jobs:
        if not job.source_id:
            continue
        detail = self.fetch_detail(job.source_id)
        if not detail:
            continue
        desc = detail.get("stellenangebotsBeschreibung", "")
        if desc and (not job.description or len(desc) > len(job.description)):
            job.description = desc
        if detail.get("homeofficemoeglich") and not job.remote:
            job.remote = True
        time.sleep(0.2)
    return jobs
```

---

### Task 3: Wire up enrichment + embeddings in `/jobs/search-boards`

**Files:**
- Modify: `src/api/routers/jobs.py` — the `search_job_boards()` function and `_upsert_job_board_jobs()`

**What:**

1. In `search_job_boards()`, after `search_all()` but before `_upsert_job_board_jobs()`, enrich the jobs:
```python
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource

arbeitsagentur = ArbeitsagenturSource()
enriched_jobs = arbeitsagentur.enrich_jobs(normalized_jobs)
```

2. In `_upsert_job_board_jobs()`, after creating a new job (around line 186), generate an embedding:
```python
# After db.add(new_job) and before newly_added += 1:
from src.services.embeddings import generate_job_embedding, embedding_to_json

if new_job.description:
    emb = generate_job_embedding(
        title=new_job.title,
        description=new_job.description,
        requirements={},
    )
    if emb:
        new_job.embedding = embedding_to_json(emb)
```

---

### Task 4: Fix 3 existing bugs

**Files:**
- Modify: `src/services/hybrid_extraction.py:122` — Workday hardcoded hash
- Modify: `src/services/hybrid_extraction.py:235-238` — Munchen bypass
- Modify: `src/services/job_discovery.py:604` — duplicate ILIKE

**Bug 1: Workday hardcoded hash** (`hybrid_extraction.py:122`)
The hash `318c8bb6f553100021d223d9780d30be` is tenant-specific. Use Workday's standard `wfp/career/careersection/alljobs/search` endpoint instead, or dynamically extract the hash from the URL.

**Bug 2: Munchen bypass** (`hybrid_extraction.py:235-238`)
Remove these two lines that unconditionally accept Munchen jobs regardless of the target cities filter:
```python
or "munchen" in location_str
or "munchen" in title_str
```

**Bug 3: Duplicate ILIKE** (`job_discovery.py:604`)
Line 604 duplicates line 602 (`CompanyModel.industry.ilike`). Replace line 604 with:
```python
CompanyModel.url.ilike(f"%{kw}%"),
```

---

### Task 5: Update tests

**Files:**
- Create: `tests/test_services/test_arbeitsagentur_detail.py`
- Update: `tests/test_api/test_search_boards.py` — mock enrich_jobs + embedding generation

**Tests for detail fetching:**
- Mock HTTPX to return HTML with embedded jobdetail JSON
- Verify description is extracted correctly
- Verify graceful None return on failures

**Tests for embedding generation in upsert:**
- Mock `generate_job_embedding` to return a test embedding
- Verify new jobs with descriptions get embeddings
- Verify jobs without descriptions don't crash

---

### Task 6: Run full test suite + verify

```bash
conda activate jobwiz_env
pytest tests/ -v
ruff check .
ruff format .
```

All 223+ existing tests should pass, plus new tests for detail fetching and embedding generation.
