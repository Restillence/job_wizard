import uuid
import os
from unittest.mock import patch, MagicMock
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Job, Resume, Company, CompanySize
from src.services.hybrid_extraction import ExtractionResult


class TestExtractJobs:
    @patch("src.api.routers.jobs.extraction_service.extract_jobs_for_companies")
    def test_extract_jobs_success(self, mock_extract, client):
        db = TestingSessionLocal()
        company = create_test_company(db, "Extract Test Corp")
        db.commit()

        mock_extract.return_value = {
            "results": [
                {
                    "company_id": company.id,
                    "company_name": "Extract Test Corp",
                    "jobs": [
                        {
                            "id": "job-1",
                            "title": "Engineer",
                            "source_url": "https://test.com/job/1",
                            "company_id": company.id,
                            "is_active": True,
                        }
                    ],
                    "newly_added": 1,
                    "updated": 0,
                }
            ],
            "total_extracted": 1,
            "total_new": 1,
            "total_updated": 0,
        }

        response = client.post(
            "/api/v1/jobs/extract", json={"company_ids": [company.id]}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_extracted"] == 1
        assert data["total_new"] == 1
        db.close()

    def test_extract_jobs_empty_company_ids(self, client):
        response = client.post("/api/v1/jobs/extract", json={"company_ids": []})

        assert response.status_code == 400


class TestMatchJobs:
    @patch("src.api.routers.jobs.json_to_embedding")
    @patch("src.api.routers.jobs.cosine_similarity")
    def test_match_jobs_success(self, mock_similarity, mock_json_to_emb, client):
        db = TestingSessionLocal()

        user_id = "test_user_id"
        company = create_test_company(db, "Match Test Corp")

        resume = Resume(
            id=str(uuid.uuid4()),
            user_id=user_id,
            file_path="uploads/resumes/test.txt",
            embedding="[0.1, 0.2, 0.3]",
        )
        db.add(resume)

        job = Job(
            id=str(uuid.uuid4()),
            company_id=company.id,
            source_url="https://match-test.com/job/1",
            title="Senior Engineer",
            description="Build things",
            embedding="[0.4, 0.5, 0.6]",
            is_active=True,
        )
        db.add(job)
        db.commit()

        mock_json_to_emb.return_value = [0.1, 0.2, 0.3]
        mock_similarity.return_value = 0.85

        response = client.post(
            "/api/v1/jobs/match", json={"user_id": user_id, "top_k": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] >= 1
        assert data["matched_jobs"][0]["similarity_score"] == 0.85

        db.close()

    def test_match_jobs_user_not_found(self, client):
        response = client.post(
            "/api/v1/jobs/match", json={"user_id": "nonexistent", "top_k": 10}
        )

        assert response.status_code == 404

    def test_match_jobs_resume_not_found(self, client):
        db = TestingSessionLocal()

        from src.models import User

        new_user = User(
            id="no_resume_user",
            email="no_resume@test.com",
            hashed_password="pwd",
        )
        db.add(new_user)
        db.commit()

        response = client.post(
            "/api/v1/jobs/match", json={"user_id": "no_resume_user", "top_k": 10}
        )

        assert response.status_code == 404

        db.close()

    @patch("src.api.routers.jobs.json_to_embedding")
    def test_match_jobs_no_active_jobs(self, mock_json_to_emb, client):
        db = TestingSessionLocal()

        user_id = "test_user_id"
        resume = Resume(
            id=str(uuid.uuid4()),
            user_id=user_id,
            file_path="uploads/resumes/test.txt",
            embedding="[0.1, 0.2, 0.3]",
        )
        db.add(resume)
        db.commit()

        mock_json_to_emb.return_value = [0.1, 0.2, 0.3]

        non_existent_company_id = str(uuid.uuid4())

        response = client.post(
            "/api/v1/jobs/match",
            json={
                "user_id": user_id,
                "company_ids": [non_existent_company_id],
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 0
        assert data["matched_jobs"] == []

        db.close()
