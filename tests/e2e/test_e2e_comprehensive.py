import pytest
import os
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.database import Base, get_db
from src.models import (
    User,
    Company,
    Job,
    Resume,
    Application,
    CompanySize,
    ApplicationStatus,
)
from src.api.deps import verify_jwt, check_rate_limit
from src.config import settings

pytestmark = pytest.mark.skipif(
    not settings.RUN_E2E_TESTS,
    reason="E2E tests disabled. Set RUN_E2E_TESTS=True",
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
    return {"user_id": "e2e_test_user"}


def override_check_rate_limit():
    return True


def mock_embedding(text: str):
    return [0.1] * 3072


def mock_discover_companies(query: str, exclude_companies=None):
    return []


def mock_scrape_jobs(url: str):
    from src.services.hybrid_extraction import ScrapedJobs, JobOpening

    return ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="Test Job",
                application_url=f"{url}/job/1",
                requirements=["Python"],
                description="Test description",
            )
        ]
    )


def mock_generate_draft(job, resume_text):
    return ("Test cover letter", "Test AI rationale")


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    app.dependency_overrides[check_rate_limit] = override_check_rate_limit

    patches = [
        patch("src.services.embeddings.generate_embedding", side_effect=mock_embedding),
        patch(
            "src.services.job_discovery.JobDiscoveryService.discover_companies",
            side_effect=mock_discover_companies,
        ),
        patch(
            "src.services.hybrid_extraction.HybridExtractionService.scrape_jobs",
            side_effect=mock_scrape_jobs,
        ),
        patch(
            "src.services.cover_letter.CoverLetterService.generate_draft",
            side_effect=mock_generate_draft,
        ),
    ]

    for p in patches:
        p.start()

    yield TestClient(app)

    for p in patches:
        p.stop()

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()


def create_unique_user(db):
    unique_id = str(uuid.uuid4())
    user = User(
        id=f"e2e_test_user_{unique_id}",
        email=f"e2e_{unique_id}@test.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    return user


def create_jwt_user(db):
    existing = db.query(User).filter(User.id == "e2e_test_user").first()
    if existing:
        return existing
    user = User(
        id="e2e_test_user",
        email="e2e_test_user@test.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    return user


def create_unique_company(db):
    unique_id = str(uuid.uuid4())
    company = Company(
        id=f"company_{unique_id}",
        name=f"E2E Company {unique_id[:8]}",
        url=f"https://e2e-{unique_id}.example.com/careers",
        city="Berlin",
        industry="Technology",
        company_size=CompanySize.startup,
    )
    db.add(company)
    db.commit()
    return company


class TestCompaniesSearch:
    def test_search_companies_local_only(self, client, db):
        for _ in range(6):
            create_unique_company(db)

        with patch(
            "src.services.job_discovery.JobDiscoveryService.discover_companies"
        ) as mock_discover:
            mock_discover.return_value = []

            response = client.get(
                "/api/v1/companies/search",
                params={"city": "Berlin"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total_found"] >= 1
        assert data["source"] == "local"

    def test_search_companies_with_keywords(self, client, db):
        for _ in range(6):
            create_unique_company(db)

        with patch(
            "src.services.job_discovery.JobDiscoveryService.discover_companies"
        ) as mock_discover:
            mock_discover.return_value = []

            response = client.get(
                "/api/v1/companies/search",
                params={"keywords": "Technology"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "companies" in data

    def test_search_companies_by_size(self, client, db):
        for _ in range(6):
            create_unique_company(db)

        with patch(
            "src.services.job_discovery.JobDiscoveryService.discover_companies"
        ) as mock_discover:
            mock_discover.return_value = []

            response = client.get(
                "/api/v1/companies/search",
                params={"company_size": "startup"},
            )
        assert response.status_code == 200
        data = response.json()
        assert all(c["company_size"] == "startup" for c in data["companies"])


class TestJobsExtract:
    def test_extract_jobs_creates_embeddings(self, client, db):
        company = create_unique_company(db)
        response = client.post(
            "/api/v1/jobs/extract",
            json={"company_ids": [company.id]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_extracted" in data
        assert data["total_extracted"] >= 1

        for result in data["results"]:
            for job in result.get("jobs", []):
                assert "id" in job
                assert "title" in job
                assert job["company_id"] == company.id

                db_job = db.query(Job).filter(Job.id == job["id"]).first()
                assert db_job is not None
                assert db_job.embedding is not None

    def test_extract_jobs_empty_company_ids(self, client):
        response = client.post(
            "/api/v1/jobs/extract",
            json={"company_ids": []},
        )
        assert response.status_code == 400


class TestJobsMatch:
    def test_match_jobs_returns_ranked_results(self, client, db):
        from src.services.embeddings import generate_embedding, embedding_to_json

        user = create_unique_user(db)
        company = create_unique_company(db)

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path="uploads/test_resume.txt",
            embedding=embedding_to_json(
                generate_embedding(
                    "Python developer with 5 years experience in FastAPI, PostgreSQL"
                )
            ),
        )
        db.add(resume)
        db.commit()

        job1 = Job(
            id=str(uuid.uuid4()),
            company_id=company.id,
            source_url=f"https://example.com/job/{uuid.uuid4()}",
            title="Senior Python Developer",
            description="Looking for experienced Python developer with FastAPI skills",
            embedding=embedding_to_json(
                generate_embedding("Senior Python developer FastAPI PostgreSQL")
            ),
            is_active=True,
        )
        job2 = Job(
            id=str(uuid.uuid4()),
            company_id=company.id,
            source_url=f"https://example.com/job/{uuid.uuid4()}",
            title="Marketing Manager",
            description="Marketing role for brand management",
            embedding=embedding_to_json(
                generate_embedding("Marketing brand management social media")
            ),
            is_active=True,
        )
        db.add_all([job1, job2])
        db.commit()

        response = client.post(
            "/api/v1/jobs/match",
            json={"user_id": user.id, "top_k": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert "matched_jobs" in data
        assert len(data["matched_jobs"]) >= 1

        python_job = next(
            (
                j
                for j in data["matched_jobs"]
                if j["title"] == "Senior Python Developer"
            ),
            None,
        )
        assert python_job is not None
        assert python_job["similarity_score"] > 0.5

    def test_match_jobs_with_company_filter(self, client, db):
        from src.services.embeddings import generate_embedding, embedding_to_json

        user = create_unique_user(db)
        company = create_unique_company(db)

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path="uploads/test_resume.txt",
            embedding=embedding_to_json(generate_embedding("Python developer")),
        )
        db.add(resume)
        db.commit()

        response = client.post(
            "/api/v1/jobs/match",
            json={
                "user_id": user.id,
                "company_ids": [company.id],
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "matched_jobs" in data

    def test_match_jobs_user_not_found(self, client):
        response = client.post(
            "/api/v1/jobs/match",
            json={"user_id": "nonexistent_user", "top_k": 10},
        )
        assert response.status_code == 404

    def test_match_jobs_resume_not_found(self, client, db):
        user = create_unique_user(db)

        response = client.post(
            "/api/v1/jobs/match",
            json={"user_id": user.id, "top_k": 10},
        )
        assert response.status_code == 404


class TestApplicationsPrepare:
    def test_prepare_application_generates_cover_letter(self, client, db):
        from src.services.embeddings import generate_embedding, embedding_to_json
        import os

        user = create_jwt_user(db)
        company = create_unique_company(db)

        os.makedirs("uploads", exist_ok=True)
        resume_file_path = "uploads/test_resume_prepare.txt"
        with open(resume_file_path, "w", encoding="utf-8") as f:
            f.write("Python developer with FastAPI experience")

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path=resume_file_path,
            embedding=embedding_to_json(
                generate_embedding("Python developer with FastAPI experience")
            ),
        )
        db.add(resume)

        job = Job(
            id=str(uuid.uuid4()),
            company_id=company.id,
            source_url=f"https://example.com/job/{uuid.uuid4()}",
            title="Software Engineer",
            description="We are looking for a software engineer with Python experience",
            embedding=embedding_to_json(
                generate_embedding("Software engineer Python development")
            ),
            is_active=True,
        )
        db.add(job)
        db.commit()

        response = client.post(
            "/api/v1/applications/prepare",
            params={"job_id": job.id, "resume_id": resume.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert "application_id" in data
        assert "cover_letter_path" in data
        assert "ai_match_rationale" in data
        assert data["status"] == "Drafted"
        assert data["similarity_score"] > 0

        app_record = (
            db.query(Application)
            .filter(Application.id == data["application_id"])
            .first()
        )
        assert app_record is not None
        assert app_record.status == ApplicationStatus.Drafted
        assert app_record.similarity_score is not None

        if os.path.exists(resume_file_path):
            os.remove(resume_file_path)

    def test_prepare_application_job_not_found(self, client, db):
        user = create_jwt_user(db)

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path="uploads/test.txt",
        )
        db.add(resume)
        db.commit()

        response = client.post(
            "/api/v1/applications/prepare",
            params={"job_id": "nonexistent_job", "resume_id": resume.id},
        )
        assert response.status_code == 404


class TestApplicationsApprove:
    def test_approve_application_not_found(self, client):
        response = client.post("/api/v1/applications/nonexistent_id/approve")
        assert response.status_code == 404


class TestPipelineSearchAndMatch:
    def test_pipeline_full_flow(self, client, db):
        from src.services.embeddings import generate_embedding, embedding_to_json

        user = create_unique_user(db)
        create_unique_company(db)

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path="uploads/test_resume.txt",
            embedding=embedding_to_json(generate_embedding("Python developer")),
        )
        db.add(resume)
        db.commit()

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "user_id": user.id,
                "city": "Berlin",
                "industry": "Technology",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "companies_found" in data
        assert "jobs_extracted" in data
        assert "matched_jobs" in data

    def test_pipeline_with_keywords(self, client, db):
        from src.services.embeddings import generate_embedding, embedding_to_json

        user = create_unique_user(db)

        resume = Resume(
            id=f"resume_{uuid.uuid4()}",
            user_id=user.id,
            file_path="uploads/test_resume.txt",
            embedding=embedding_to_json(generate_embedding("Python developer")),
        )
        db.add(resume)
        db.commit()

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "user_id": user.id,
                "keywords": ["Python", "FastAPI"],
                "top_k": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "matched_jobs" in data

    def test_pipeline_no_resume(self, client, db):
        user = create_unique_user(db)

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={"user_id": user.id, "top_k": 5},
        )
        assert response.status_code == 404


class TestResumesUpload:
    def test_upload_resume_with_pii_stripping(self, client, db):
        user = create_jwt_user(db)

        test_content = """
        RESUME
        
        Name: John Doe
        Email: john.doe@example.com
        Phone: +49 123 456789
        
        Experience:
        - Software Engineer at TechCorp (2020-2023)
        - Python, FastAPI, PostgreSQL
        """

        response = client.post(
            "/api/v1/resumes/upload",
            files={"file": ("test_resume.txt", test_content.encode(), "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data

        assert os.path.exists(data["file_path"])
        with open(data["file_path"], "r", encoding="utf-8") as f:
            content = f.read()
            assert "John Doe" not in content
            assert "john.doe@example.com" not in content
            assert "[REDACTED]" in content or "REDACTED" in content

        if os.path.exists(data["file_path"]):
            os.remove(data["file_path"])

    def test_upload_resume_creates_embedding_in_class(self, client, db):
        user = create_jwt_user(db)
        test_content = "Python developer with machine learning experience"

        response = client.post(
            "/api/v1/resumes/upload",
            files={"file": ("embedding_test.txt", test_content.encode(), "text/plain")},
        )
        assert response.status_code == 200

        resume = db.query(Resume).filter(Resume.user_id == user.id).first()
        assert resume is not None
        assert resume.embedding is not None

        if os.path.exists(resume.file_path):
            os.remove(resume.file_path)


class TestEmbeddingsLive:
    def test_generate_embedding_live(self):
        from src.services.embeddings import generate_embedding

        embedding = generate_embedding("This is a test for live embedding generation")
        assert embedding is not None
        assert len(embedding) == 3072
        assert all(isinstance(x, float) for x in embedding)

    def test_cosine_similarity_live(self):
        from src.services.embeddings import generate_embedding, cosine_similarity

        emb1 = generate_embedding("Python software developer")
        emb2 = generate_embedding("Software engineer Python")

        assert emb1 is not None and emb2 is not None

        sim = cosine_similarity(emb1, emb2)
        assert sim > 0.9
