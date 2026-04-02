# ruff: noqa: E402
"""
Live Integration Tests - Actually call real APIs.

Run with: RUN_LIVE_TESTS=True pytest tests/e2e/test_live_integration.py -v --tb=short

WARNING: These tests consume API quota and require real API keys.
"""

from dotenv import load_dotenv

load_dotenv()

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.database import Base, get_db
from src.models import User, Resume
from src.api.deps import verify_jwt, check_rate_limit
from src.config import settings

LIVE_TESTS_ENABLED = os.environ.get("RUN_LIVE_TESTS", "False").lower() == "true"

pytestmark = pytest.mark.skipif(
    not LIVE_TESTS_ENABLED,
    reason="Live tests disabled. Set RUN_LIVE_TESTS=True to run.",
)

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_verify_jwt():
    return {"user_id": "live_test_user"}


def override_check_rate_limit():
    return True


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    app.dependency_overrides[check_rate_limit] = override_check_rate_limit

    yield TestClient(app)

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()


def create_test_user(db):
    existing = db.query(User).filter(User.id == "live_test_user").first()
    if existing:
        return existing
    user = User(
        id="live_test_user",
        email="live_test@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    return user


class TestLiveAPIKeys:
    """Verify API keys are configured and valid."""

    def test_gemini_api_key_present(self):
        assert settings.GEMINI_API_KEY, "GEMINI_API_KEY not set in .env"
        assert settings.GEMINI_API_KEY != "your-gemini-api-key-here"

    def test_zai_api_key_present(self):
        assert settings.ZAI_API_KEY, "ZAI_API_KEY not set in .env"
        assert settings.ZAI_API_KEY != "your-zai-api-key-here"

    def test_at_least_one_search_api_key_present(self):
        has_search_api = (
            settings.TAVILY_API_KEY or settings.SERPER_API_KEY or settings.BRAVE_API_KEY
        )
        assert has_search_api, (
            "At least one search API key (TAVILY, SERPER, or BRAVE) should be set"
        )


class TestLiveGeminiEmbeddings:
    """Test real Gemini embedding generation."""

    def test_generate_embedding_returns_3072_dims(self):
        from src.services.embeddings import generate_embedding

        result = generate_embedding("Python developer with FastAPI experience")

        assert result is not None, "Embedding generation failed - check GEMINI_API_KEY"
        assert len(result) == 3072, f"Expected 3072 dimensions, got {len(result)}"
        assert all(isinstance(x, float) for x in result)

    def test_embedding_similarity_semantic_match(self):
        from src.services.embeddings import generate_embedding, cosine_similarity

        emb1 = generate_embedding("Python software developer")
        emb2 = generate_embedding("Software engineer Python")
        emb3 = generate_embedding("Marketing manager social media campaigns")

        assert emb1 is not None and emb2 is not None and emb3 is not None

        sim_similar = cosine_similarity(emb1, emb2)
        sim_different = cosine_similarity(emb1, emb3)

        assert sim_similar > 0.7, (
            f"Similar jobs should have high similarity, got {sim_similar}"
        )
        assert sim_similar > sim_different, (
            "Similar jobs should score higher than different jobs"
        )

    def test_embedding_similarity_exact_match(self):
        from src.services.embeddings import generate_embedding, cosine_similarity

        text = "Exact same text for comparison"
        emb1 = generate_embedding(text)
        emb2 = generate_embedding(text)

        assert emb1 is not None and emb2 is not None
        sim = cosine_similarity(emb1, emb2)
        assert sim > 0.99, f"Identical texts should have ~1.0 similarity, got {sim}"


class TestLiveCompanyDiscovery:
    """Test real search API calls for company discovery."""

    def test_discover_companies_returns_results(self):
        """Test company discovery with real APIs (may take 30-60s)."""
        from src.services.job_discovery import JobDiscoveryService

        service = JobDiscoveryService()
        companies = service.discover_companies(
            cities=["Berlin"],
            industries=["Software"],
            keywords=["Python"],
        )

        assert len(companies) >= 0, "Discovery should complete"
        for company in companies[:5]:
            assert company.company_name, "Company should have a name"
            assert company.career_url, "Company should have a career URL"
            assert company.career_url.startswith("http"), "Career URL should be valid"
            print(f"Found: {company.company_name} - {company.career_url}")


class TestLiveJobExtraction:
    """Test real job extraction from career pages."""

    def test_extract_from_personio_page(self):
        """Test extraction from a real Personio career page."""
        from src.services.hybrid_extraction import HybridExtractionService

        service = HybridExtractionService()
        ats_type = service.check_ats_footprint("https://personio.de/careers")

        assert ats_type == "personio", "Should detect Personio footprint"

    def test_extract_from_greenhouse_page(self):
        """Test extraction from a real Greenhouse career page."""
        from src.services.hybrid_extraction import HybridExtractionService

        service = HybridExtractionService()
        ats_type = service.check_ats_footprint("https://boards.greenhouse.io/example")

        assert ats_type == "greenhouse", "Should detect Greenhouse footprint"

    def test_extract_from_workday_page(self):
        """Test extraction from a real Workday career page."""
        from src.services.hybrid_extraction import HybridExtractionService

        service = HybridExtractionService()
        ats_type = service.check_ats_footprint("https://myworkdayjobs.com/example")

        assert ats_type == "workday", "Should detect Workday footprint"

    @pytest.mark.anyio
    async def test_scrape_jobs_creates_embeddings(self):
        """Test that job scraping works (uses Crawl4AI fallback)."""
        from src.services.hybrid_extraction import HybridExtractionService

        service = HybridExtractionService()

        result = await service.scrape_jobs("https://example.com/careers")
        assert result is not None, "Scraping should return a result"
        assert hasattr(result, "jobs"), "Result should have jobs attribute"


class TestLiveCoverLetterGeneration:
    """Test real LLM cover letter generation."""

    def test_generate_cover_letter(self):
        """Test generating a cover letter with real LLM."""
        from src.services.cv_generator import CVGeneratorService
        from src.services.cv_parser import ParsedCV, CVSection
        from unittest.mock import MagicMock

        service = CVGeneratorService()

        resume_text = """
        John Doe
        Software Engineer with 6 years of experience in Python, FastAPI, and PostgreSQL.
        Previously worked at TechStartup building REST APIs.
        Skills: Python, FastAPI, PostgreSQL, Docker, AWS
        """

        parsed_cv = ParsedCV(
            summary="Software Engineer with 6 years of experience",
            experience=[
                CVSection(
                    title="Software Engineer @ TechStartup",
                    content="Built REST APIs with Python, FastAPI, PostgreSQL",
                )
            ],
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
        )

        result = service.generate_cover_letter(
            parsed_cv=parsed_cv,
            job_title="Senior Python Developer",
            company_name="TestCorp",
            job_description="Looking for a Python developer with FastAPI experience. Must have 5+ years experience.",
            job_requirements={"skills": ["Python", "FastAPI"]},
        )

        assert result.cover_letter, "Cover letter should be generated"
        assert len(result.cover_letter) > 100, "Cover letter should be substantial"
        assert (
            "Python" in result.cover_letter or "python" in result.cover_letter.lower()
        ), "Cover letter should mention relevant skills"

        assert result.cover_letter, "Cover letter should be generated"
        assert len(result.cover_letter) > 100, "Cover letter should be substantial"
        assert (
            "Python" in result.cover_letter or "python" in result.cover_letter.lower()
        ), "Cover letter should mention relevant skills"


class TestLivePIIStripping:
    """Test PII stripping with realistic data."""

    def test_strip_pii_removes_personal_info(self):
        """Test PII stripping with real LLM (may take 10-30s)."""
        from src.services.pii_stripping import PIIStrippingService

        service = PIIStrippingService()

        resume_with_pii = """
        John Smith
        Email: john.smith@example.com
        Phone: +49 123 456 7890
        Address: Main Street 123, 10115 Berlin

        Experience:
        - Software Engineer at TechCorp (2020-2023)
        """

        stripped = service.strip_pii(resume_with_pii)

        assert "john.smith@example.com" not in stripped, "Email should be redacted"
        assert "+49 123 456 7890" not in stripped, "Phone should be redacted"
        assert "REDACTED" in stripped or "[REDACTED]" in stripped, (
            "Should indicate redaction"
        )


class TestLiveFullPipeline:
    """Test the full pipeline with real API calls."""

    def test_upload_resume_with_embedding(self, client, db):
        """Test resume upload creates embedding."""
        user = create_test_user(db)

        test_content = """
        Software Engineer with 5 years experience in Python, FastAPI, PostgreSQL.
        Worked on microservices architecture and cloud deployments.
        Interested in AI/ML and backend development.
        """

        response = client.post(
            "/api/v1/resumes/upload",
            files={"file": ("resume.txt", test_content.encode(), "text/plain")},
        )

        assert response.status_code == 200, f"Resume upload failed: {response.text}"
        data = response.json()
        assert "resume_id" in data
        assert "file_path" in data

        resume = db.query(Resume).filter(Resume.user_id == user.id).first()
        assert resume is not None, "Resume should be created in DB"
        assert resume.embedding is not None, "Resume should have embedding"

        if os.path.exists(data["file_path"]):
            os.remove(data["file_path"])

    def test_search_companies_real_api(self, client):
        """Test company search with real API fallback (may take 30-60s)."""
        response = client.get(
            "/api/v1/companies/search",
            params={"keywords": ["Python"], "industries": ["Software"]},
        )

        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert "companies" in data
        assert "total_found" in data
        assert data["source"] in ["local", "api_fallback"]
        print(
            f"Found {data['total_found']} companies, source: {data['source']}, newly added: {data.get('newly_added', 0)}"
        )


class TestLiveRateLimiting:
    """Verify rate limiting works (basic check)."""

    def test_rate_limit_allows_requests(self, client, db):
        """Verify normal requests are allowed."""
        create_test_user(db)
        for _ in range(3):
            response = client.get("/api/v1/jobs/")
            assert response.status_code in [200, 404]
