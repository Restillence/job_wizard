from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.models import Application, Job, Resume, ApplicationStatus
from src.services.cover_letter import CoverLetterService
import uuid
import os

router = APIRouter(prefix="/applications", tags=["applications"])
cover_letter_service = CoverLetterService()

@router.post("/draft")
async def draft_application(
    job_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit)
):
    # Fetch job and resume
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_info["user_id"]).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Ensure resume file exists
    if not os.path.exists(resume.file_path):
        raise HTTPException(status_code=500, detail="Resume file missing")

    with open(resume.file_path, "r", encoding="utf-8") as f:
        resume_text = f.read()

    # Generate Draft
    try:
        cover_letter_text, ai_rationale = cover_letter_service.generate_draft(job, resume_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")

    # Save cover letter
    upload_dir = "uploads/cover_letters"
    os.makedirs(upload_dir, exist_ok=True)
    
    cl_id = str(uuid.uuid4())
    cl_file_path = f"{upload_dir}/{cl_id}.txt"
    with open(cl_file_path, "w", encoding="utf-8") as f:
        f.write(cover_letter_text)

    # Save application
    app = Application(
        user_id=user_info["user_id"],
        job_id=job.id,
        status=ApplicationStatus.Drafted,
        ai_match_rationale=ai_rationale,
        cover_letter_file_path=cl_file_path
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {"message": "Draft created", "application_id": app.id, "file_path": cl_file_path}

@router.post("/{app_id}/approve")
async def approve_application(
    app_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit)
):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user_info["user_id"]).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status != ApplicationStatus.Drafted:
        raise HTTPException(status_code=400, detail="Application is not in Drafted status")

    app.status = ApplicationStatus.Approved
    db.commit()

    return {"message": f"Application {app_id} approved"}
