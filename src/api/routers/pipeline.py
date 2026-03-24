from typing import List, Optional
from fastapi import APIRouter, Depends, Body, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService
from src.services.hybrid_extraction import HybridExtractionService
from src.services.embeddings import (
    cosine_similarity,
    json_to_embedding,
    generate_resume_embedding,
    embedding_to_json,
)
from src.models import Job, Resume, User, CompanySize

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
discovery_service = JobDiscoveryService()
extraction_service = HybridExtractionService()


class PipelineRequest(BaseModel):
    cities: Optional[List[str]] = Field(None, description="Filter by cities (OR logic)")
    industries: Optional[List[str]] = Field(
        None, description="Filter by industries (OR logic)"
    )
    keywords: Optional[List[str]] = Field(None, description="Keywords for search")
    company_size: Optional[str] = Field(
        None, description="startup, hidden_champion, or enterprise"
    )
    user_id: str = Field(..., description="User ID to match jobs for")
    top_k: int = Field(20, description="Number of matched jobs to return")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cities": ["Berlin", "Munich"],
                "industries": ["AI", "FinTech"],
                "keywords": ["python"],
                "company_size": "startup",
                "user_id": "uuid",
                "top_k": 20,
            }
        }
    }


class PipelineMatchedJob(BaseModel):
    job_id: str
    title: str
    company_name: str
    company_id: str
    similarity_score: float


class PipelineResponse(BaseModel):
    companies_found: int
    companies_new: int
    jobs_extracted: int
    jobs_new: int
    matched_jobs: List[PipelineMatchedJob]


@router.post("/search-and-match", response_model=PipelineResponse)
async def search_and_match(
    request: PipelineRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    One-shot job discovery with matching.

    1. Search companies (local DB + API fallback with two-step extraction)
    2. Extract jobs from found companies
    3. Match user profile against jobs
    4. Save search to user history (max 5 per user)
    """
    company_size_enum = None
    if request.company_size:
        try:
            company_size_enum = CompanySize(request.company_size)
        except ValueError:
            company_size_enum = None

    companies_result = await discovery_service.search_companies(
        db=db,
        user_id=request.user_id,
        cities=request.cities,
        industries=request.industries,
        keywords=request.keywords,
        company_size=company_size_enum,
    )

    company_ids = [c["id"] for c in companies_result.companies]

    jobs_result = {"total_extracted": 0, "total_new": 0}
    if company_ids:
        jobs_result = await extraction_service.extract_jobs_for_companies(db, company_ids)

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        return PipelineResponse(
            companies_found=companies_result.total_found,
            companies_new=companies_result.newly_added,
            jobs_extracted=jobs_result["total_extracted"],
            jobs_new=jobs_result["total_new"],
            matched_jobs=[],
        )

    resume = db.query(Resume).filter(Resume.user_id == request.user_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found for user")

    resume_embedding = json_to_embedding(resume.embedding)
    if not resume_embedding and resume.file_path:
        import os

        if os.path.exists(resume.file_path):
            with open(resume.file_path, "r", encoding="utf-8") as f:
                resume_text = f.read()

            resume_embedding = generate_resume_embedding(
                resume_text, user.zusatz_infos or {}
            )
            if resume_embedding:
                resume.embedding = embedding_to_json(resume_embedding)
                db.commit()

    if not resume_embedding:
        raise HTTPException(
            status_code=500, detail="Failed to generate resume embedding"
        )

    jobs_query = db.query(Job).filter(Job.is_active == True)  # noqa: E712

    if company_ids:
        jobs_query = jobs_query.filter(Job.company_id.in_(company_ids))

    jobs = jobs_query.all()

    job_scores = []
    for job in jobs:
        job_embedding = json_to_embedding(job.embedding)
        if job_embedding:
            score = cosine_similarity(resume_embedding, job_embedding)
            job_scores.append((job, score))

    job_scores.sort(key=lambda x: x[1], reverse=True)
    top_jobs = job_scores[: request.top_k]

    matched_jobs = []
    for job, score in top_jobs:
        company_name = job.company.name if job.company else "Unknown"
        matched_jobs.append(
            PipelineMatchedJob(
                job_id=job.id,
                title=job.title,
                company_name=company_name,
                company_id=job.company_id,
                similarity_score=round(score, 4),
            )
        )

    return PipelineResponse(
        companies_found=companies_result.total_found,
        companies_new=companies_result.newly_added,
        jobs_extracted=jobs_result["total_extracted"],
        jobs_new=jobs_result["total_new"],
        matched_jobs=matched_jobs,
    )
