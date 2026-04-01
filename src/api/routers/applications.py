from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.models import Application, Job, Resume, ApplicationStatus
from src.services.cv_parser import CVParserService
from src.services.cv_generator import CVGeneratorService
from src.services.docx_renderer import render_cv, render_cover_letter
from src.services.pii_stripping import PIIStrippingService
from src.services.embeddings import cosine_similarity, json_to_embedding
import uuid
import os

router = APIRouter(prefix="/applications", tags=["applications"])
cv_parser = CVParserService()
cv_generator = CVGeneratorService()
pii_service = PIIStrippingService()


@router.post("/prepare")
async def prepare_application(
    job_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == user_info["user_id"])
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if not os.path.exists(resume.file_path):
        raise HTTPException(status_code=500, detail="Resume file missing")

    with open(resume.file_path, "r", encoding="utf-8") as f:
        resume_text = f.read()

    stripped_resume_text = pii_service.strip_pii(resume_text)

    similarity_score: Optional[float] = None
    if resume.embedding and job.embedding:
        resume_emb = json_to_embedding(resume.embedding)
        job_emb = json_to_embedding(job.embedding)
        if resume_emb and job_emb:
            similarity_score = cosine_similarity(resume_emb, job_emb)

    try:
        parsed_cv = cv_parser.parse(stripped_resume_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV parsing failed: {str(e)}")

    company_name = job.company.name if job.company else "Unknown"

    try:
        tailored_cv = cv_generator.tailor_cv(
            parsed_cv=parsed_cv,
            job_title=job.title,
            job_description=job.description or "",
            job_requirements=job.extracted_requirements or {},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV tailoring failed: {str(e)}")

    try:
        cover_letter_result = cv_generator.generate_cover_letter(
            parsed_cv=parsed_cv,
            job_title=job.title,
            company_name=company_name,
            job_description=job.description or "",
            job_requirements=job.extracted_requirements or {},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Cover letter generation failed: {str(e)}"
        )

    upload_dir = "uploads/applications"
    os.makedirs(upload_dir, exist_ok=True)

    app_id = str(uuid.uuid4())
    cv_path = f"{upload_dir}/{app_id}_cv.docx"
    cl_path = f"{upload_dir}/{app_id}_cover_letter.docx"

    try:
        render_cv(tailored_cv, parsed_cv, cv_path)
        render_cover_letter(cover_letter_result, parsed_cv, company_name, cl_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOCX rendering failed: {str(e)}")

    app = Application(
        user_id=user_info["user_id"],
        job_id=job.id,
        status=ApplicationStatus.Drafted,
        ai_match_rationale=cover_letter_result.ai_match_rationale,
        cover_letter_file_path=cl_path,
        similarity_score=similarity_score,
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {
        "message": "Application prepared",
        "application_id": app.id,
        "cv_path": cv_path,
        "cover_letter_path": cl_path,
        "ai_match_rationale": cover_letter_result.ai_match_rationale,
        "similarity_score": similarity_score,
        "tailoring_notes": tailored_cv.tailoring_notes,
        "status": "Drafted",
    }


@router.post("/{app_id}/approve")
async def approve_application(
    app_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    app = (
        db.query(Application)
        .filter(Application.id == app_id, Application.user_id == user_info["user_id"])
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status != ApplicationStatus.Drafted:
        raise HTTPException(
            status_code=400, detail="Application is not in Drafted status"
        )

    app.status = ApplicationStatus.Approved
    db.commit()

    return {"message": f"Application {app_id} approved"}
