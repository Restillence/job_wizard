import uuid
import os
from unittest.mock import patch, MagicMock
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Job, Resume, Application, ApplicationStatus
from src.services.cv_parser import ParsedCV, CVSection
from src.services.cv_generator import TailoredCV, TailoredSection, CoverLetterResult


def _make_parsed_cv():
    return ParsedCV(
        full_name="[REDACTED]",
        email="[REDACTED]",
        phone="[REDACTED]",
        summary="Experienced developer",
        experience=[
            CVSection(
                title="Senior Dev @ TechCorp | 2021-Present",
                content="• Built Python systems\n• Led team",
            )
        ],
        education=[
            CVSection(
                title="B.Sc. Computer Science | TU Berlin | 2019", content="CS degree"
            )
        ],
        skills=["Python", "Docker", "Kubernetes"],
        languages=["English (Fluent)", "German (Native)"],
    )


def _make_tailored_cv():
    return TailoredCV(
        summary="Experienced Python developer",
        experience=[
            TailoredSection(
                title="Senior Dev @ TechCorp | 2021-Present",
                content="• Built Python systems\n• Led team",
            )
        ],
        education=[
            TailoredSection(
                title="B.Sc. Computer Science | TU Berlin | 2019", content="CS degree"
            )
        ],
        skills=["Python", "Docker", "Kubernetes"],
        languages=["English (Fluent)", "German (Native)"],
        tailoring_notes="Reordered skills to emphasize Python",
    )


def _make_cover_letter():
    return CoverLetterResult(
        cover_letter="Dear Hiring Manager,\n\nI am writing to apply...",
        ai_match_rationale="User matches 3/5 requirements including Python",
    )


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
        patch("src.api.routers.applications.cv_parser.parse") as mock_parse,
        patch("src.api.routers.applications.cv_generator.tailor_cv") as mock_tailor,
        patch(
            "src.api.routers.applications.cv_generator.generate_cover_letter"
        ) as mock_cl,
        patch("src.api.routers.applications.pii_service.strip_pii") as mock_pii,
        patch("src.api.routers.applications.render_cv") as mock_render_cv,
        patch("src.api.routers.applications.render_cover_letter") as mock_render_cl,
    ):
        mock_parse.return_value = _make_parsed_cv()
        mock_tailor.return_value = _make_tailored_cv()
        mock_cl.return_value = _make_cover_letter()
        mock_pii.return_value = "My resume content [REDACTED]"
        mock_render_cv.return_value = "uploads/applications/test_cv.docx"
        mock_render_cl.return_value = "uploads/applications/test_cl.docx"

        response = client.post(
            "/api/v1/applications/prepare",
            params={"job_id": job.id, "resume_id": resume.id},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Application prepared"
    assert "application_id" in data
    assert "similarity_score" in data
    assert "cv_path" in data
    assert "cover_letter_path" in data
    assert data["status"] == "Drafted"
    assert data["tailoring_notes"] == "Reordered skills to emphasize Python"

    app_id = data["application_id"]
    app = db.query(Application).filter(Application.id == app_id).first()
    assert app is not None
    assert app.status == ApplicationStatus.Drafted
    assert app.similarity_score is not None
    assert abs(app.similarity_score - 1.0) < 0.0001

    os.remove(resume_file_path)
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
        patch("src.api.routers.applications.cv_parser.parse") as mock_parse,
        patch("src.api.routers.applications.cv_generator.tailor_cv") as mock_tailor,
        patch(
            "src.api.routers.applications.cv_generator.generate_cover_letter"
        ) as mock_cl,
        patch("src.api.routers.applications.pii_service.strip_pii") as mock_pii,
        patch("src.api.routers.applications.render_cv") as mock_render_cv,
        patch("src.api.routers.applications.render_cover_letter") as mock_render_cl,
    ):
        mock_parse.return_value = _make_parsed_cv()
        mock_tailor.return_value = _make_tailored_cv()
        mock_cl.return_value = _make_cover_letter()
        mock_pii.return_value = "My resume content [REDACTED]"
        mock_render_cv.return_value = "uploads/applications/test_cv.docx"
        mock_render_cl.return_value = "uploads/applications/test_cl.docx"

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
