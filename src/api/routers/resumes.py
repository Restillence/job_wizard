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
import io

router = APIRouter(prefix="/resumes", tags=["resumes"])
pii_service = PIIStrippingService()


def _extract_text_from_pdf(content: bytes) -> str:
    import fitz

    doc = fitz.open(stream=content, filetype="pdf")
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def _extract_text_from_docx(content: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


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

    filename = file.filename or "resume.txt"
    ext = os.path.splitext(filename)[1].lower()
    allowed_extensions = {".txt", ".pdf", ".docx"}
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    content = await file.read()

    if ext == ".txt":
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")
    elif ext == ".pdf":
        text_content = _extract_text_from_pdf(content)
    elif ext == ".docx":
        text_content = _extract_text_from_docx(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    if not text_content or not text_content.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    stripped_content = pii_service.strip_pii(text_content)

    file_id = str(uuid.uuid4())
    original_path = f"{upload_dir}/{file_id}{ext}"
    text_path = f"{upload_dir}/{file_id}.txt"

    with open(original_path, "wb") as f:
        f.write(content)

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(stripped_content)

    embedding = generate_embedding(stripped_content)
    if not embedding:
        os.remove(original_path)
        os.remove(text_path)
        raise HTTPException(
            status_code=500, detail="Failed to generate resume embedding"
        )

    resume = Resume(
        user_id=user_info["user_id"],
        file_path=text_path,
        original_file_path=original_path,
        embedding=embedding_to_json(embedding),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return UploadResponse(
        message="Resume uploaded, PII stripped, and embedding generated",
        file_path=text_path,
        resume_id=resume.id,
    )
