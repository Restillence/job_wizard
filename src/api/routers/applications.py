from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import Application, ApplicationStatus
import uuid

router = APIRouter(prefix="/applications", tags=["applications"])

@router.post("/draft")
async def draft_application(
    job_id: str,
    db: Session = Depends(get_db)
):
    # Logic to generate cover letter draft
    app_id = str(uuid.uuid4())
    return {"message": "Draft created", "application_id": app_id}

@router.post("/{app_id}/approve")
async def approve_application(
    app_id: str,
    db: Session = Depends(get_db)
):
    return {"message": f"Application {app_id} approved"}
