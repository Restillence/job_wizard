import uuid
import os
from unittest.mock import patch, MagicMock
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Job, Resume


def test_search_and_match_success(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    db.query(Job).delete()
    db.query(Resume).filter(Resume.user_id == user_id).delete()
    db.commit()

    company = create_test_company(db, "Pipeline Test Co")
    job = Job(
        id=str(uuid.uuid4()),
        source_url="http://pipeline-test.com/job/1",
        title="Senior Python Developer",
        company_id=company.id,
        description="Python, FastAPI, PostgreSQL",
        embedding="[0.1, 0.1, 0.1]",
        is_active=True,
    )
    db.add(job)

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/pipeline_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("Experienced Python developer")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding="[0.1, 0.1, 0.1]",
    )
    db.add(resume)
    db.commit()

    with patch("src.api.routers.pipeline.search_all", return_value=[]):
        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "cities": ["Berlin"],
                "industries": ["Tech"],
                "user_id": user_id,
                "top_k": 10,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["board_jobs_found"] == 0
    assert len(data["matched_jobs"]) == 1
    assert data["matched_jobs"][0]["title"] == "Senior Python Developer"
    assert data["matched_jobs"][0]["similarity_score"] > 0.99

    os.remove(resume_file_path)
    db.close()


def test_search_and_match_no_resume(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    db.query(Resume).filter(Resume.user_id == user_id).delete()
    db.commit()

    with patch("src.api.routers.pipeline.search_all", return_value=[]):
        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "user_id": user_id,
                "top_k": 10,
            },
        )

    assert response.status_code == 404
    db.close()


def test_search_and_match_with_company_size(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    db.query(Job).delete()
    db.query(Resume).filter(Resume.user_id == user_id).delete()
    db.commit()

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/pipeline_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("Developer resume")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding="[0.2, 0.2, 0.2]",
    )
    db.add(resume)
    db.commit()

    with (
        patch("src.api.routers.pipeline.search_all", return_value=[]),
        patch(
            "src.api.routers.pipeline.discovery_service.search_companies"
        ) as mock_search,
    ):
        mock_search.return_value = MagicMock(
            companies=[],
            total_found=0,
            newly_added=0,
            source="local",
        )

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "company_size": "startup",
                "user_id": user_id,
                "top_k": 5,
                "deep_search": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["companies_found"] == 0
    assert data["matched_jobs"] == []

    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args[1]
    assert call_kwargs["company_size"].value == "startup"

    os.remove(resume_file_path)
    db.close()


def test_search_and_match_with_keywords(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/pipeline_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("Python developer")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding="[0.3, 0.3, 0.3]",
    )
    db.add(resume)
    db.commit()

    with (
        patch("src.api.routers.pipeline.search_all", return_value=[]),
        patch(
            "src.api.routers.pipeline.discovery_service.search_companies"
        ) as mock_search,
    ):
        mock_search.return_value = MagicMock(
            companies=[],
            total_found=0,
            newly_added=0,
            source="local",
        )

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "keywords": ["python", "django"],
                "user_id": user_id,
                "top_k": 10,
                "deep_search": True,
            },
        )

    assert response.status_code == 200

    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args[1]
    assert call_kwargs["keywords"] == ["python", "django"]

    os.remove(resume_file_path)
    db.close()


def test_search_and_match_multiple_cities_industries(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/pipeline_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("Developer resume")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding="[0.4, 0.4, 0.4]",
    )
    db.add(resume)
    db.commit()

    with (
        patch("src.api.routers.pipeline.search_all", return_value=[]),
        patch(
            "src.api.routers.pipeline.discovery_service.search_companies"
        ) as mock_search,
    ):
        mock_search.return_value = MagicMock(
            companies=[],
            total_found=0,
            newly_added=0,
            source="local",
        )

        response = client.post(
            "/api/v1/pipeline/search-and-match",
            json={
                "cities": ["Berlin", "Munich", "Frankfurt"],
                "industries": ["AI", "FinTech"],
                "keywords": ["Python"],
                "user_id": user_id,
                "top_k": 10,
                "deep_search": True,
            },
        )

    assert response.status_code == 200

    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args[1]
    assert call_kwargs["cities"] == ["Berlin", "Munich", "Frankfurt"]
    assert call_kwargs["industries"] == ["AI", "FinTech"]
    assert call_kwargs["keywords"] == ["Python"]

    os.remove(resume_file_path)
    db.close()
