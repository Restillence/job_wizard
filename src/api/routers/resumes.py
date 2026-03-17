from fastapi import APIRouter, UploadFile, File, Depends
from src.services.pii_stripping import PIIStrippingService
from src.database import get_db
from sqlalchemy.orm import Session
from src.api.deps import verify_jwt, check_rate_limit
import os
import uuid

router = APIRouter(prefix="/resumes", tags=["resumes"])
pii_service = PIIStrippingService()


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    # Ensure directory exists
    upload_dir = "uploads/resumes"
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    file_path = f"{upload_dir}/{file_id}.txt"

    # Read file content and strip PII
    content = await file.read()
    text_content = content.decode("utf-8")
    stripped_content = pii_service.strip_pii(text_content)

    # Save stripped content
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(stripped_content)

    return {"message": "Resume uploaded and PII stripped", "file_path": file_path}
