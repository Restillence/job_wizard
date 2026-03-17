"""
E2E Test Script for JobWiz
Tests the full pipeline with real API keys.

Prerequisites:
1. Set ZAI_API_KEY and GEMINI_API_KEY in .env
2. Run: python init_db.py
3. Run: uvicorn src.main:app --reload --port 8000
"""

import httpx
import os
import sys

BASE_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint"""
    response = httpx.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    print("✓ Health check passed")


def test_companies_search():
    """Test company search"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/companies/search",
        params={"city": "Berlin", "industry": "Tech"},
    )
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Found {data['total_found']} companies")
    return data


def test_jobs_extract(company_ids):
    """Test job extraction"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/jobs/extract",
        json={"company_ids": company_ids},
    )
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Extracted {data['total_extracted']} jobs")
    return data


def test_jobs_match(user_id):
    """Test job matching"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/jobs/match",
        json={"user_id": user_id, "top_k": 10},
    )
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Matched {data['total_matches']} jobs")
    return data


def test_upload_resume():
    """Test resume upload"""
    test_content = b"John Doe - Python Developer - john@example.com"

    files = {"file": ("resume.txt", test_content, "text/plain")}
    response = httpx.post(
        f"{BASE_URL}/api/v1/resumes/upload",
        files=files,
    )
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Resume uploaded to {data['file_path']}")
    return data["file_path"]


def test_pipeline():
    """Test full pipeline"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/pipeline/search-and-match",
        json={
            "city": "Berlin",
            "industry": "AI",
            "keywords": ["python"],
            "user_id": "test_user_id",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Pipeline complete:")
    print(f"  Companies: {data['companies_found']}")
    print(f"  Jobs: {data['jobs_extracted']}")
    print(f"  Matches: {len(data['matched_jobs'])}")
    return data


def main():
    print("=" * 60)
    print("JobWiz E2E Test")
    print("=" * 60)

    # Check API keys
    from src.config import settings

    missing = settings.validate_required_keys()
    if missing:
        print(f"❌ Missing API keys: {', '.join(missing)}")
        print("Please set them in .env file")
        sys.exit(1)

    print("✓ All required API keys present")

    # Run tests
    test_health()

    companies = test_companies_search()

    if companies["total_found"] > 0:
        company_ids = [c["id"] for c in companies["companies"]]
        jobs = test_jobs_extract(company_ids)

    resume_path = test_upload_resume()

    match = test_jobs_match("test_user_id")

    test_pipeline()

    print("\n" + "=" * 60)
    print("All E2E tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
