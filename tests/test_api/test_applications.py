import uuid
import os
from unittest.mock import patch
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Job, Resume, Application, ApplicationStatus


def test_prepare_application(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    company = create_test_company(db, "Test Inc")
    job = Job(
        id=str(uuid.uuid4()),
        source_url="http://test.com",
        title="Dev",
        company_id=company.id,
        description="Desc",
        embedding=[0.1] * 3072,
    )
    db.add(job)

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/test_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("My resume content")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding=[0.1] * 3072,
    )
    db.add(resume)
    db.commit()

    with (
        patch(
            "src.api.routers.applications.cover_letter_service.generate_draft"
        ) as mock_gen,
        patch("src.api.routers.applications.pii_service.strip_pii") as mock_pii,
    ):
        mock_gen.return_value = ("Draft letter content", "Good match")
        mock_pii.return_value = "My resume content [REDACTED]"

        response = client.post(
            "/api/v1/applications/prepare",
            params={"job_id": job.id, "resume_id": resume.id},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Application prepared"
    assert "application_id" in data
    assert "similarity_score" in data
    assert data["status"] == "Drafted"

    app_id = data["application_id"]
    app = db.query(Application).filter(Application.id == app_id).first()
    assert app is not None
    assert app.status == ApplicationStatus.Drafted
    assert app.ai_match_rationale == "Good match"
    assert app.similarity_score is not None
    assert abs(app.similarity_score - 1.0) < 0.0001

    os.remove(resume_file_path)
    if app.cover_letter_file_path and os.path.exists(app.cover_letter_file_path):
        os.remove(app.cover_letter_file_path)
    db.close()


def test_prepare_application_no_embeddings(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    company = create_test_company(db, "Test Inc 2")
    job = Job(
        id=str(uuid.uuid4()),
        source_url="http://test-no-embed.com",
        title="Dev",
        company_id=company.id,
        description="Desc",
        embedding=None,
    )
    db.add(job)

    os.makedirs("uploads/resumes", exist_ok=True)
    resume_file_path = f"uploads/resumes/test_resume_{uuid.uuid4()}.txt"
    with open(resume_file_path, "w") as f:
        f.write("My resume content")

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_file_path,
        embedding=None,
    )
    db.add(resume)
    db.commit()

    with (
        patch(
            "src.api.routers.applications.cover_letter_service.generate_draft"
        ) as mock_gen,
        patch("src.api.routers.applications.pii_service.strip_pii") as mock_pii,
    ):
        mock_gen.return_value = ("Draft letter content", "Good match")
        mock_pii.return_value = "My resume content [REDACTED]"

        response = client.post(
            "/api/v1/applications/prepare",
            params={"job_id": job.id, "resume_id": resume.id},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["similarity_score"] is None

    app_id = data["application_id"]
    app = db.query(Application).filter(Application.id == app_id).first()
    assert app.similarity_score is None

    os.remove(resume_file_path)
    if app.cover_letter_file_path and os.path.exists(app.cover_letter_file_path):
        os.remove(app.cover_letter_file_path)
    db.close()


def test_approve_application(client):
    db = TestingSessionLocal()
    user_id = "test_user_id"

    company = create_test_company(db, "Approve Inc")
    job = Job(
        id=str(uuid.uuid4()),
        source_url="http://test2.com",
        title="Dev",
        company_id=company.id,
        description="Desc",
    )
    db.add(job)

    app = Application(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_id=job.id,
        status=ApplicationStatus.Drafted,
    )
    db.add(app)
    db.commit()

    response = client.post(f"/api/v1/applications/{app.id}/approve")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == f"Application {app.id} approved"

    db.refresh(app)
    assert app.status == ApplicationStatus.Approved
    db.close()
