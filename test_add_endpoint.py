"""
Live integration test script for POST /api/v1/jobs/add endpoint.

Tests all code paths:
  1. raw_text only
  2. URL only (company career page)
  3. Aggregator URL without raw_text → 400 error
  4. Aggregator URL + raw_text fallback
  5. Neither url nor raw_text → 400 error
  6. Duplicate detection (same source_url twice)
  7. Verify DB state (job + company records, embedding present)

Requires: running server on localhost:8000, test user in DB, ZAI_API_KEY + GEMINI_API_KEY in .env

Usage:
  python test_add_endpoint.py
  python test_add_endpoint.py --base-url http://localhost:8000
"""

import sys
import json
import time
import argparse
from datetime import datetime, timezone

if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

BASE_URL = "http://localhost:8000"
PASS = 0
FAIL = 0
SKIP = 0


def _print_result(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def _print_skip(name: str, reason: str):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {name} — {reason}")


def _add_job(client: httpx.Client, payload: dict) -> httpx.Response:
    return client.post(f"{BASE_URL}/api/v1/jobs/add", json=payload, timeout=180)


def test_01_no_input(client: httpx.Client):
    """Neither url nor raw_text → 400."""
    r = _add_job(client, {})
    _print_result(
        "Empty payload → 400",
        r.status_code == 400,
        f"got {r.status_code}",
    )


def test_02_raw_text_only(client: httpx.Client):
    """raw_text only → 201-ish, job created."""
    payload = {
        "raw_text": """
Senior Python Developer — TechCorp GmbH

Location: Berlin, Germany
Type: Full-time

About the role:
We are looking for a Senior Python Developer to join our backend team.
You will design and build scalable APIs using FastAPI and PostgreSQL.

Requirements:
- 5+ years of Python experience
- FastAPI or Django
- PostgreSQL, SQLAlchemy
- Docker, CI/CD
- Git

Benefits:
- 30 days vacation
- Remote-first
- Education budget
"""
    }
    r = _add_job(client, payload)
    ok = r.status_code == 200
    _print_result("raw_text only → 200", ok, f"got {r.status_code}")

    if ok:
        data = r.json()
        _print_result(
            "  title extracted", bool(data.get("title")), repr(data.get("title"))
        )
        _print_result(
            "  company_name present",
            bool(data.get("company_name")),
            repr(data.get("company_name")),
        )
        _print_result(
            "  is_new=True", data.get("is_new") is True, repr(data.get("is_new"))
        )
        _print_result(
            "  source=manual_text",
            data.get("source") == "manual_text",
            repr(data.get("source")),
        )
        _print_result(
            "  job_id present", bool(data.get("job_id")), repr(data.get("job_id"))
        )
        _print_result(
            "  company_id present",
            bool(data.get("company_id")),
            repr(data.get("company_id")),
        )
        return data
    return None


def test_03_aggregator_url_no_text(client: httpx.Client):
    """Aggregator URL without raw_text → 400 with helpful message."""
    payload = {"url": "https://de.indeed.com/viewjob?jk=someid123"}
    r = _add_job(client, payload)
    ok = r.status_code == 400
    _print_result("Aggregator URL without raw_text → 400", ok, f"got {r.status_code}")

    if ok:
        detail = r.json().get("detail", "")
        _print_result(
            "  mentions aggregator",
            "aggregator" in detail.lower() or "paste" in detail.lower(),
            repr(detail[:100]),
        )


def test_04_aggregator_url_with_text(client: httpx.Client):
    """Aggregator URL + raw_text → skips scraping, uses text."""
    payload = {
        "url": "https://de.indeed.com/viewjob?jk=test456",
        "raw_text": """
Data Engineer — DataWorks AG
Location: Munich, Germany

Requirements:
- Python, SQL, Spark
- Airflow or Prefect
- AWS or GCP
- ETL pipeline design
""",
    }
    r = _add_job(client, payload)
    ok = r.status_code == 200
    _print_result("Aggregator URL + raw_text → 200", ok, f"got {r.status_code}")

    if ok:
        data = r.json()
        _print_result(
            "  job created", bool(data.get("job_id")), repr(data.get("job_id"))
        )
        return data
    return None


def test_05_company_url(client: httpx.Client):
    """Real company URL → scrapes and extracts.

    Uses a job page that is known to work with Crawl4AI.
    This test is slow (60-120s for LLM reasoning).
    """
    url = input("\n  Enter a job URL to test (or press Enter to skip): ").strip()
    if not url:
        _print_skip("Company URL scraping", "no URL provided")
        return None

    print(f"  Scraping {url} ... (this may take 60-120s)")
    start = time.time()
    r = _add_job(client, {"url": url})
    elapsed = time.time() - start

    ok = r.status_code == 200
    _print_result(
        f"Company URL → 200 ({elapsed:.0f}s)",
        ok,
        f"got {r.status_code}",
    )

    if ok:
        data = r.json()
        _print_result(
            "  title extracted", bool(data.get("title")), repr(data.get("title"))
        )
        _print_result(
            "  company_name present",
            bool(data.get("company_name")),
            repr(data.get("company_name")),
        )
        _print_result(
            "  source=manual_url",
            data.get("source") == "manual_url",
            repr(data.get("source")),
        )
        _print_result(
            "  description present",
            bool(data.get("description")),
            f"{len(data.get('description', ''))} chars",
        )
        return data
    else:
        print(f"  Response: {r.text[:300]}")
    return None


def test_06_duplicate_detection(client: httpx.Client, first_result: dict | None):
    """Submit the same source_url again → is_new=False."""
    if not first_result:
        _print_skip("Duplicate detection", "no previous job to re-submit")
        return

    payload = {
        "raw_text": """
Senior Python Developer — TechCorp GmbH
Location: Berlin, Germany
""",
    }
    r = _add_job(client, payload)
    if r.status_code == 200:
        data = r.json()
        _print_result(
            "Duplicate → is_new=False",
            data.get("is_new") is False,
            f"is_new={data.get('is_new')}",
        )
        _print_result(
            "Same job_id",
            data.get("job_id") == first_result.get("job_id"),
            f"{data.get('job_id')} vs {first_result.get('job_id')}",
        )
    else:
        _print_result(
            "Duplicate detection", False, f"status {r.status_code}: {r.text[:200]}"
        )


def test_07_verify_db_state(client: httpx.Client, first_result: dict | None):
    """Query the job endpoint to verify DB state."""
    if not first_result:
        _print_skip("DB state verification", "no previous job")
        return

    job_id = first_result.get("job_id")
    _company_id = first_result.get("company_id")

    r = client.get(f"{BASE_URL}/api/v1/jobs/", timeout=10)
    if r.status_code == 200:
        jobs = r.json()
        found = any(j.get("id") == job_id for j in jobs)
        _print_result("Job present in list endpoint", found, f"job_id={job_id}")
    else:
        _print_result("Job list endpoint", False, f"status {r.status_code}")


def test_08_embedding_check(first_result: dict | None):
    """Check that the job has an embedding by querying DB directly."""
    if not first_result:
        _print_skip("Embedding check", "no previous job")
        return

    try:
        from src.database import SessionLocal
        from src.models import Job

        db = SessionLocal()
        job = db.query(Job).filter(Job.id == first_result["job_id"]).first()
        if job:
            has_embedding = job.embedding is not None
            emb_len = 0
            if has_embedding:
                emb_data = job.embedding
                if isinstance(emb_data, str):
                    emb_data = json.loads(emb_data)
                emb_len = len(emb_data) if isinstance(emb_data, list) else 0
            _print_result(
                "Job has embedding",
                has_embedding,
                f"{emb_len} dimensions" if has_embedding else "None",
            )
            if has_embedding:
                _print_result(
                    "Embedding dimension count",
                    emb_len == 3072,
                    f"got {emb_len}",
                )
            _print_result(
                "Job has extracted_requirements",
                bool(job.extracted_requirements),
                repr(str(job.extracted_requirements)[:80])
                if job.extracted_requirements
                else "None",
            )
            _print_result(
                "Job.is_active=True",
                job.is_active is True,
                repr(job.is_active),
            )
            _print_result(
                "Job.first_seen_at set",
                job.first_seen_at is not None,
                repr(job.first_seen_at),
            )
            _print_result(
                "Job.company relationship works",
                job.company is not None,
                repr(job.company.name if job.company else None),
            )
        else:
            _print_result("Job found in DB", False, f"id={first_result['job_id']}")
        db.close()
    except Exception as e:
        _print_result("DB embedding check", False, str(e))


def main():
    parser = argparse.ArgumentParser(description="Test /api/v1/jobs/add endpoint")
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Server base URL"
    )
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    print(f"\n{'=' * 60}")
    print(f"  Testing POST {BASE_URL}/api/v1/jobs/add")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 60}\n")

    client = httpx.Client(timeout=180)

    # Quick health check
    try:
        r = client.get(f"{BASE_URL}/docs", timeout=5)
        if r.status_code not in (200, 404):
            print(f"  WARNING: Server returned {r.status_code} on /docs")
    except httpx.ConnectError:
        print("  ERROR: Cannot connect to server. Is it running?")
        print("  Start it with: python -m uvicorn src.main:app --reload --port 8000")
        sys.exit(1)

    print("  --- Test 1: Empty payload ---")
    test_01_no_input(client)

    print("\n  --- Test 2: raw_text only ---")
    first_result = test_02_raw_text_only(client)

    print("\n  --- Test 3: Aggregator URL without raw_text ---")
    test_03_aggregator_url_no_text(client)

    print("\n  --- Test 4: Aggregator URL + raw_text ---")
    test_04_aggregator_url_with_text(client)

    print("\n  --- Test 5: Company URL (interactive) ---")
    test_05_company_url(client)

    print("\n  --- Test 6: Duplicate detection ---")
    test_06_duplicate_detection(client, first_result)

    print("\n  --- Test 7: DB state verification ---")
    test_07_verify_db_state(client, first_result)

    print("\n  --- Test 8: Embedding & model field check ---")
    test_08_embedding_check(first_result)

    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print(f"{'=' * 60}\n")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
