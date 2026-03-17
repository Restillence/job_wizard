from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from src.services.pii_stripping import PIIStrippingService
from src.services.embeddings import generate_embedding, embedding_to_json
from src.database import get_db
from src.models import Resume
from sqlalchemy.orm import Session
from src.api.deps import verify_jwt, check_rate_limit
import os
import uuid

router = APIRouter(prefix="/resumes", tags=["resumes"])
pii_service = PIIStrippingService()


class UploadResponse(BaseModel):
    message: str
    file_path: str
    resume_id: str


@router.post("/upload", response_model=UploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    upload_dir = "uploads/resumes"
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    file_path = f"{upload_dir}/{file_id}.txt"

    content = await file.read()
    text_content = content.decode("utf-8")
    stripped_content = pii_service.strip_pii(text_content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(stripped_content)

    embedding = generate_embedding(stripped_content)
    if not embedding:
        os.remove(file_path)
        raise HTTPException(
            status_code=500, detail="Failed to generate resume embedding"
        )

    resume = Resume(
        user_id=user_info["user_id"],
        file_path=file_path,
        embedding=embedding_to_json(embedding),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return UploadResponse(
        message="Resume uploaded, PII stripped, and embedding generated",
        file_path=file_path,
        resume_id=resume.id,
    )
