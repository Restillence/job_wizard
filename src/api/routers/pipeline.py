from typing import List, Optional
from datetime import datetime, timezone
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
    generate_job_embedding,
)
from src.models import Job, Resume, User, CompanySize
from src.services.job_sources import search_all
from src.services.job_sources.base import SearchParams, NormalizedJob
from src.services.job_sources.company_resolver import resolve_or_create_company
from src.services.job_sources.dedup import merge_job_data

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
    deep_search: bool = Field(
        False,
        description="Also run company discovery + scraping (slower, more exclusive jobs)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "cities": ["Berlin", "Munich"],
                "industries": ["AI", "FinTech"],
                "keywords": ["python"],
                "company_size": "startup",
                "user_id": "uuid",
                "top_k": 20,
                "deep_search": False,
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
    board_jobs_found: int = 0
    board_jobs_new: int = 0
    companies_found: int = 0
    companies_new: int = 0
    jobs_extracted: int = 0
    jobs_new: int = 0
    matched_jobs: List[PipelineMatchedJob]


def _get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_job_to_dict(job: NormalizedJob) -> dict:
    return {
        "title": job.title,
        "company_name": job.company_name,
        "source_url": job.source_url,
        "source": job.source,
        "source_id": job.source_id,
        "description": job.description,
        "location_city": job.location_city,
        "location_region": job.location_region,
        "location_country": job.location_country,
        "remote": job.remote,
        "job_types": job.job_types,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "tags": job.tags,
        "visa_sponsorship": job.visa_sponsorship,
        "raw_data": job.raw_data,
    }


def _upsert_board_jobs(
    db: Session,
    normalized_jobs: List[NormalizedJob],
) -> tuple[List[Job], int, int]:
    now = _get_utc_now()
    newly_added = 0
    updated = 0
    jobs_list: List[Job] = []

    for norm_job in normalized_jobs:
        dedup_hash = norm_job.dedup_hash

        existing_job = db.query(Job).filter(Job.dedup_hash == dedup_hash).first()

        if existing_job:
            incoming = _normalized_job_to_dict(norm_job)
            merged = merge_job_data(
                {
                    "sources": existing_job.sources or [],
                    "description": existing_job.description,
                    "salary_min": existing_job.salary_min,
                    "salary_max": existing_job.salary_max,
                    "salary_currency": existing_job.salary_currency,
                    "visa_sponsorship": existing_job.visa_sponsorship,
                    "tags": existing_job.tags,
                    "location_region": existing_job.location_region,
                    "location_country": existing_job.location_country,
                    "job_types": existing_job.job_types,
                    "posted_at": existing_job.posted_at,
                    "expires_at": existing_job.expires_at,
                },
                incoming,
                norm_job.source,
            )
            existing_job.sources = merged["sources"]
            existing_job.last_seen_at = now
            existing_job.is_active = True

            backfill_map = {
                "salary_min": existing_job.salary_min,
                "salary_max": existing_job.salary_max,
                "salary_currency": existing_job.salary_currency,
                "visa_sponsorship": existing_job.visa_sponsorship,
                "tags": existing_job.tags,
                "location_region": existing_job.location_region,
                "location_country": existing_job.location_country,
                "job_types": existing_job.job_types,
                "posted_at": existing_job.posted_at,
                "expires_at": existing_job.expires_at,
            }
            for field, current_val in backfill_map.items():
                if current_val is None and merged.get(field) is not None:
                    setattr(existing_job, field, merged[field])

            if merged.get("description") and len(merged["description"] or "") > len(
                existing_job.description or ""
            ):
                existing_job.description = merged["description"]

            updated += 1
            jobs_list.append(existing_job)
        else:
            company, _ = resolve_or_create_company(db, norm_job)
            new_job = Job(
                company_id=company.id,
                source_url=norm_job.source_url,
                title=norm_job.title,
                description=norm_job.description or "",
                source=norm_job.source,
                source_id=norm_job.source_id,
                dedup_hash=dedup_hash,
                sources=[norm_job.source],
                location_city=norm_job.location_city,
                location_region=norm_job.location_region,
                location_country=norm_job.location_country,
                remote=norm_job.remote,
                job_types=norm_job.job_types,
                salary_min=norm_job.salary_min,
                salary_max=norm_job.salary_max,
                salary_currency=norm_job.salary_currency,
                posted_at=norm_job.posted_at,
                expires_at=norm_job.expires_at,
                tags=norm_job.tags,
                visa_sponsorship=norm_job.visa_sponsorship,
                raw_data=norm_job.raw_data,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(new_job)
            if new_job.description:
                emb = generate_job_embedding(
                    title=new_job.title,
                    description=new_job.description,
                    requirements={},
                    tags=new_job.tags,
                )
                if emb:
                    new_job.embedding = embedding_to_json(emb)
            newly_added += 1
            jobs_list.append(new_job)

    if newly_added > 0 or updated > 0:
        db.commit()
        for job in jobs_list:
            db.refresh(job)

    return jobs_list, newly_added, updated


@router.post("/search-and-match", response_model=PipelineResponse)
async def search_and_match(
    request: PipelineRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    One-shot job discovery with matching.

    Primary: Job board APIs (Arbeitsagentur, Arbeitnow).
    Optional deep_search: Company discovery + scraping for exclusive jobs.

    1. Search job boards, save to DB
    2. (If deep_search) Discover + extract from company career pages
    3. Match user profile against all active jobs
    """
    board_jobs_new = 0
    board_jobs: List[NormalizedJob] = []

    search_query = " ".join(request.keywords) if request.keywords else None
    city = request.cities[0] if request.cities else None
    country = "DE"

    try:
        board_params = SearchParams(
            query=search_query,
            city=city,
            country=country,
            page=1,
            per_page=50,
            keywords=request.keywords,
        )
        board_jobs = search_all(board_params)
        if board_jobs:
            _, board_jobs_new, _ = _upsert_board_jobs(db, board_jobs)
    except Exception as e:
        print(f"Board search failed: {e}")

    companies_found = 0
    companies_new = 0
    jobs_extracted = 0
    jobs_new = 0

    if request.deep_search:
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

        companies_found = companies_result.total_found
        companies_new = companies_result.newly_added

        company_ids = [c["id"] for c in companies_result.companies]
        if company_ids:
            jobs_result = await extraction_service.extract_jobs_for_companies(
                db, company_ids
            )
            jobs_extracted = jobs_result["total_extracted"]
            jobs_new = jobs_result["total_new"]

    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        return PipelineResponse(
            board_jobs_found=len(board_jobs) if board_jobs else 0,
            board_jobs_new=board_jobs_new,
            companies_found=companies_found,
            companies_new=companies_new,
            jobs_extracted=jobs_extracted,
            jobs_new=jobs_new,
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
        board_jobs_found=len(board_jobs) if board_jobs else 0,
        board_jobs_new=board_jobs_new,
        companies_found=companies_found,
        companies_new=companies_new,
        jobs_extracted=jobs_extracted,
        jobs_new=jobs_new,
        matched_jobs=matched_jobs,
    )
