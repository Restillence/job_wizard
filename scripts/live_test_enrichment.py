"""
Live E2E test for the Arbeitsagentur enrichment + embedding pipeline.

Usage:
    python scripts/live_test_enrichment.py
    RUN_LIVE_TESTS=True pytest scripts/live_test_enrichment.py -v
"""

# ── Configure search params here ──────────────────────────────────────────
QUERY = "Data Science"
CITY = "Frankfurt"
COUNTRY = "DE"
KEYWORDS = None  # e.g. ["Python", "SQL"]
PER_PAGE = 3
# ──────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv

load_dotenv()

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.base import SearchParams
from src.services.embeddings import generate_job_embedding, embedding_to_json

LIVE = os.environ.get("RUN_LIVE_TESTS", "False").lower() == "true"

PARAMS = SearchParams(
    query=QUERY,
    city=CITY,
    country=COUNTRY,
    keywords=KEYWORDS,
    per_page=PER_PAGE,
)


def main():
    source = ArbeitsagenturSource()

    print(f"1. Searching Arbeitsagentur for '{QUERY}' jobs in {CITY}...")
    jobs = source.fetch(PARAMS)
    print(f"   Found {len(jobs)} jobs (thin, no descriptions)")

    if not jobs:
        print("   No jobs found. Try different params at the top of this script.")
        return

    for j in jobs:
        desc = j.description or "None"
        print(f"   - {j.title} @ {j.company_name} | desc={desc!r}")

    print()
    print("2. Enriching with full descriptions from detail pages...")
    enriched = source.enrich_jobs(jobs)

    print()
    for j in enriched:
        desc_len = len(j.description) if j.description else 0
        print(f"   {j.title}")
        print(f"   Company: {j.company_name}")
        print(f"   Description: {desc_len} chars")
        print(f"   Remote: {j.remote}")
        print()

    if enriched and enriched[0].description:
        print("3. Generating embedding...")
        emb = generate_job_embedding(
            title=enriched[0].title,
            description=enriched[0].description,
            requirements={},
        )
        if emb:
            print(f"   Embedding generated: {len(emb)} dimensions")
            print(f"   First 5 values: {emb[:5]}")
            json_emb = embedding_to_json(emb)
            print(f"   JSON size: {len(json_emb)} bytes")
        else:
            print("   FAILED: embedding is None (check GEMINI_API_KEY)")
    else:
        print("   Skipped embedding test (no description)")

    print()
    print("Done. Full pipeline: search -> enrich -> embed")


if LIVE:
    import pytest

    def test_search_returns_thin_results():
        source = ArbeitsagenturSource()
        jobs = source.fetch(PARAMS)
        assert len(jobs) > 0
        assert jobs[0].description is None

    def test_enrich_backfills_descriptions():
        source = ArbeitsagenturSource()
        jobs = source.fetch(PARAMS)
        enriched = source.enrich_jobs(jobs)
        assert len(enriched) > 0
        assert enriched[0].description is not None
        assert len(enriched[0].description) > 100

    def test_embedding_generated_from_enriched_job():
        source = ArbeitsagenturSource()
        jobs = source.fetch(PARAMS)
        enriched = source.enrich_jobs(jobs)
        assert enriched[0].description
        emb = generate_job_embedding(
            title=enriched[0].title,
            description=enriched[0].description,
            requirements={},
        )
        assert emb is not None
        assert len(emb) == 3072

else:
    import pytest

    pytestmark = pytest.mark.skipif(
        not LIVE, reason="Live tests disabled. Set RUN_LIVE_TESTS=True to run."
    )


if __name__ == "__main__":
    main()
