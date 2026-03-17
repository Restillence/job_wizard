from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from src.database import get_db
from sqlalchemy.orm import Session
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService, Company
from src.services.hybrid_extraction import HybridExtractionService
from src.services.embeddings import (
    cosine_similarity,
    json_to_embedding,
    generate_resume_embedding,
    embedding_to_json,
)
from src.models import Job, Resume, User

router = APIRouter(prefix="/jobs", tags=["jobs"])
discovery_service = JobDiscoveryService()
extraction_service = HybridExtractionService()


class DiscoverQuery(BaseModel):
    query: str = Field(
        ...,
        description=(
            "The search query for job discovery. "
            "TIP: Avoid generic searches like 'data science frankfurt'. "
            "Instead, use search operators or target specific niches to bypass job boards like LinkedIn."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {"query": "Data Science jobs Frankfurt site:careers.*.com"}
        }
    }


class DiscoverResponse(BaseModel):
    message: str
    query: str
    companies: List[Company]


class ExtractRequest(BaseModel):
    company_ids: List[str] = Field(
        ..., description="List of company IDs to extract jobs from"
    )

    model_config = {
        "json_schema_extra": {"example": {"company_ids": ["uuid1", "uuid2"]}}
    }


class JobResponse(BaseModel):
    id: str
    title: str
    source_url: str
    company_id: str
    is_active: bool


class ExtractResponse(BaseModel):
    results: List[dict]
    total_extracted: int
    total_new: int
    total_updated: int


class MatchRequest(BaseModel):
    user_id: str = Field(..., description="User ID to match jobs for")
    company_ids: Optional[List[str]] = Field(
        None, description="Optional filter by company IDs"
    )
    top_k: int = Field(20, description="Number of results to return")

    model_config = {
        "json_schema_extra": {
            "example": {"user_id": "uuid", "company_ids": ["uuid1"], "top_k": 20}
        }
    }


class MatchedJob(BaseModel):
    job_id: str
    title: str
    company_name: str
    company_id: str
    similarity_score: float
    is_new_match: bool


class MatchResponse(BaseModel):
    matched_jobs: List[MatchedJob]
    total_matches: int


@router.post("/discover", response_model=DiscoverResponse)
async def discover_jobs(
    query: DiscoverQuery = Body(
        ...,
        openapi_examples={
            "Example 1 (Operators)": {
                "summary": "Using search operators",
                "value": {"query": "Data Science jobs Frankfurt site:careers.*.com"},
            },
            "Example 2 (Exclude Job Boards)": {
                "summary": "Excluding LinkedIn and StepStone",
                "value": {
                    "query": "AI Engineer Berlin intitle:careers -linkedin -stepstone"
                },
            },
            "Example 3 (Targeted Niches)": {
                "summary": "Specific AI Startups",
                "value": {"query": "top AI startups hiring in Berlin 2026"},
            },
        },
    ),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    try:
        companies = discovery_service.discover_companies(query.query)
        return {
            "message": "Job discovery successful",
            "query": query.query,
            "companies": companies,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract", response_model=ExtractResponse)
async def extract_jobs(
    request: ExtractRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Extract jobs from specified company career pages.

    - Checks for ATS footprints (Personio, Workday, Greenhouse) for fast extraction
    - Falls back to Crawl4AI for custom sites
    - Upserts jobs: updates existing, adds new with embeddings
    """
    if not request.company_ids:
        raise HTTPException(status_code=400, detail="company_ids is required")

    try:
        result = extraction_service.extract_jobs_for_companies(db, request.company_ids)
        return ExtractResponse(
            results=result["results"],
            total_extracted=result["total_extracted"],
            total_new=result["total_new"],
            total_updated=result["total_updated"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match", response_model=MatchResponse)
async def match_jobs(
    request: MatchRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Vector match user profile against jobs using cosine similarity.

    - Gets user's resume embedding (generates if needed)
    - Computes similarity against job embeddings
    - Returns ranked job list (no text generation yet - JIT pattern)
    """
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    resume = db.query(Resume).filter(Resume.user_id == request.user_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found for user")

    resume_embedding = json_to_embedding(resume.embedding)
    if not resume_embedding:
        if not resume.file_path:
            raise HTTPException(status_code=400, detail="Resume file not found")

        import os

        if not os.path.exists(resume.file_path):
            raise HTTPException(status_code=400, detail="Resume file missing")

        with open(resume.file_path, "r", encoding="utf-8") as f:
            resume_text = f.read()

        resume_embedding = generate_resume_embedding(
            resume_text, user.zusatz_infos or {}
        )
        if resume_embedding:
            resume.embedding = embedding_to_json(resume_embedding)
            db.commit()
        else:
            raise HTTPException(
                status_code=500, detail="Failed to generate resume embedding"
            )

    jobs_query = db.query(Job).filter(Job.is_active == True)  # noqa: E712

    if request.company_ids:
        jobs_query = jobs_query.filter(Job.company_id.in_(request.company_ids))

    jobs = jobs_query.all()

    if not jobs:
        return MatchResponse(matched_jobs=[], total_matches=0)

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
            MatchedJob(
                job_id=job.id,
                title=job.title,
                company_name=company_name,
                company_id=job.company_id,
                similarity_score=round(score, 4),
                is_new_match=True,
            )
        )

    return MatchResponse(matched_jobs=matched_jobs, total_matches=len(matched_jobs))
