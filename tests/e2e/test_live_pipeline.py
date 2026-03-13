import pytest
import os
from fastapi.testclient import TestClient
from src.main import app
from src.config import settings

# Skip this entire file if the E2E flag is not True
pytestmark = pytest.mark.skipif(
    not settings.RUN_E2E_TESTS,
    reason="E2E tests disabled by default. Set RUN_E2E_TESTS=True in config to run."
)

def test_live_pii_stripping_pipeline():
    """
    THIS TEST USES REAL Z.AI API CREDITS.
    It uploads a realistic document string and verifies the LLM
    can successfully identify and strip the sensitive info.
    """
    client = TestClient(app)
    
    # Create a realistic-looking text file string instead of just a single line
    test_content = """
    RESUME
    
    Name: Maximilian Mustermann
    Email: max.mustermann@gmail.com
    Phone: +49 176 12345678
    
    Professional Experience:
    Software Engineer at TechCorp GmbH (2020-2023)
    - Developed scalable Python microservices
    - Worked extensively with PostgreSQL and Docker
    """
    
    with open("live_test_resume.txt", "w", encoding="utf-8") as f:
        f.write(test_content)
        
    try:
        with open("live_test_resume.txt", "rb") as f:
            response = client.post(
                "/api/v1/resumes/upload",
                files={"file": ("live_test_resume.txt", f, "text/plain")}
            )
            
        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data
        
        file_path = data["file_path"]
        assert os.path.exists(file_path)
        
        with open(file_path, "r", encoding="utf-8") as f:
            stripped_content = f.read()
            
            # The LLM should have removed the specific PII
            assert "Maximilian Mustermann" not in stripped_content
            assert "max.mustermann@gmail.com" not in stripped_content
            assert "+49 176 12345678" not in stripped_content
            
            # The LLM should have left the non-PII intact (with reasonable leniency for formatting)
            assert "TechCorp" in stripped_content or "TechCorp GmbH" in stripped_content
            assert "Python" in stripped_content
            assert "[REDACTED]" in stripped_content
            
            print("\n--- LIVE LLM STRIPPING RESULT ---")
            print(stripped_content)
            print("---------------------------------")
            
    finally:
        # Cleanup
        if os.path.exists("live_test_resume.txt"):
            os.remove("live_test_resume.txt")
        if "file_path" in locals() and os.path.exists(file_path):
            os.remove(file_path)

def test_live_job_discovery_pipeline():
    """
    THIS TEST USES REAL Z.AI API CREDITS AND DUCKDUCKGO SEARCH.
    It performs an actual search and ensures the response matches the expected schema.
    """
    client = TestClient(app)
    query = "SAP career page software engineering Frankfurt"
    
    response = client.post(
        "/api/v1/jobs/discover",
        json={"query": query}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job discovery successful"
    assert "companies" in data
    assert len(data["companies"]) > 0
    
    company = data["companies"][0]
    assert "company_name" in company
    assert "career_url" in company
    assert company["career_url"].startswith("http")
    
    print("\n--- LIVE DISCOVERY RESULT ---")
    for c in data["companies"]:
        print(f"Company: {c['company_name']} - URL: {c['career_url']}")
    print("-----------------------------")
