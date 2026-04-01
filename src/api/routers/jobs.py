from typing import Any, Dict, List, Optional
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from src.database import get_db
from sqlalchemy.orm import Session
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService, Company, CompanySize
from src.services.hybrid_extraction import (
    HybridExtractionService,
    ScrapedJobs,
    JobOpening,
)
from src.services.embeddings import (
    cosine_similarity,
    json_to_embedding,
    generate_resume_embedding,
    embedding_to_json,
    generate_job_embedding,
)
from src.models import Job, Resume, User, Company as CompanyModel
from src.services.job_sources import search_all
from src.services.job_sources.base import SearchParams, NormalizedJob
from src.services.job_sources.company_resolver import resolve_or_create_company
from src.services.job_sources.dedup import merge_job_data
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource


router = APIRouter(prefix="/jobs", tags=["jobs"])
discovery_service = JobDiscoveryService()
extraction_service = HybridExtractionService()


class SearchBoardsRequest(BaseModel):
    query: Optional[str] = Field(None, description="Free-text search query")
    city: Optional[str] = Field(None, description="City filter")
    country: str = Field("DE", description="ISO 2-letter country code")
    keywords: Optional[List[str]] = Field(None, description="Keyword filters")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(25, ge=1, le=100, description="Results per page")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "Python Developer",
                "city": "Berlin",
                "country": "DE",
                "keywords": ["Python", "FastAPI"],
            }
        }
    }


class SearchBoardsJob(BaseModel):
    id: str
    title: str
    company_name: str
    source_url: str
    source: str
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    remote: bool = False
    is_new: bool


class SearchBoardsResponse(BaseModel):
    jobs: List[SearchBoardsJob]
    total_found: int
    newly_added: int
    updated: int


def _get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_job_to_dict(job: NormalizedJob) -> Dict[str, Any]:
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


def _upsert_job_board_jobs(
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


@router.post("/search-boards", response_model=SearchBoardsResponse)
async def search_job_boards(
    request: SearchBoardsRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Search external job board APIs (Arbeitsagentur, Arbeitnow) and save results.

    - Queries multiple job boards in parallel
    - Deduplicates results by content fingerprint
    - Auto-creates company records from job data
    - Enriches jobs with full descriptions from detail pages
    - Generates embeddings for new jobs with descriptions
    """
    params = SearchParams(
        query=request.query,
        city=request.city,
        country=request.country,
        page=request.page,
        per_page=request.per_page,
        keywords=request.keywords,
    )

    try:
        normalized_jobs = search_all(params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job board search failed: {e}")

    if not normalized_jobs:
        return SearchBoardsResponse(jobs=[], total_found=0, newly_added=0, updated=0)

    arbeitsagentur = ArbeitsagenturSource()
    normalized_jobs = arbeitsagentur.enrich_jobs(normalized_jobs)

    try:
        jobs_list, newly_added, updated = _upsert_job_board_jobs(db, normalized_jobs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job save failed: {e}")

    result_jobs = []
    for job in jobs_list:
        company_name = job.company.name if job.company else "Unknown"
        is_new = newly_added > 0 and any(
            j.id == job.id for j in jobs_list[:newly_added]
        )
        result_jobs.append(
            SearchBoardsJob(
                id=job.id,
                title=job.title,
                company_name=company_name,
                source_url=job.source_url,
                source=job.source,
                location_city=job.location_city,
                location_country=job.location_country,
                remote=job.remote or False,
                is_new=is_new,
            )
        )

    return SearchBoardsResponse(
        jobs=result_jobs,
        total_found=len(result_jobs),
        newly_added=newly_added,
        updated=updated,
    )


class DiscoverRequest(BaseModel):
    cities: Optional[List[str]] = Field(None, description="Filter by cities (OR logic)")
    industries: Optional[List[str]] = Field(
        None, description="Filter by industries (OR logic)"
    )
    keywords: Optional[List[str]] = Field(None, description="Keywords for search")
    company_size: Optional[str] = Field(
        None, description="startup, hidden_champion, or enterprise"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "cities": ["Berlin"],
                "industries": ["AI"],
                "keywords": ["Python", "FastAPI"],
                "company_size": "startup",
            }
        }
    }


class DiscoverResponse(BaseModel):
    message: str
    companies: List[Company]
    total_found: int


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


class AddJobRequest(BaseModel):
    url: Optional[str] = Field(
        None,
        description="Direct URL to the job posting page. Works best with company career pages.",
    )
    raw_text: Optional[str] = Field(
        None,
        description="Pasted job description text. Use when URL scraping fails or for aggregator sites (Indeed, Stepstone, etc.).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "By URL (company career page)",
                    "value": {
                        "url": "https://careers.company.com/jobs/123",
                    },
                },
                {
                    "summary": "By pasted text (for aggregator sites)",
                    "value": {
                        "raw_text": "Senior Python Developer at TechCorp...",
                    },
                },
                {
                    "summary": "URL + text fallback",
                    "value": {
                        "url": "https://de.indeed.com/viewjob?jk=abc",
                        "raw_text": "Job title: Senior Python Developer\nCompany: TechCorp\n...",
                    },
                },
            ]
        }
    }


class AddJobResponse(BaseModel):
    job_id: str
    title: str
    company_name: str
    company_id: str
    location: Optional[str] = None
    description: Optional[str] = None
    source: str
    is_new: bool


_AGGREGATOR_DOMAINS = {
    "indeed.com",
    "stepstone.de",
    "linkedin.com",
    "glassdoor.com",
    "xing.com",
    "karriere.at",
    "monster.com",
    "monster.de",
    "arbeitsagentur.de",
    "jobware.de",
    "jobscout24.de",
    "stellenanzeigen.de",
}


def _is_aggregator(hostname: str) -> bool:
    host_lower = hostname.lower()
    return any(domain in host_lower for domain in _AGGREGATOR_DOMAINS)


@router.post("/discover", response_model=DiscoverResponse)
async def discover_jobs(
    request: DiscoverRequest = Body(
        ...,
        openapi_examples={
            "Example 1 (Berlin AI)": {
                "summary": "AI companies in Berlin",
                "value": {
                    "cities": ["Berlin"],
                    "industries": ["AI"],
                    "keywords": ["Python"],
                    "company_size": "startup",
                },
            },
            "Example 2 (Multiple Cities)": {
                "summary": "FinTech in Berlin and Munich",
                "value": {
                    "cities": ["Berlin", "Munich"],
                    "industries": ["FinTech"],
                    "keywords": ["Backend"],
                },
            },
        },
    ),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    try:
        company_size_enum = None
        if request.company_size:
            try:
                company_size_enum = CompanySize(request.company_size)
            except ValueError:
                pass

        companies = await discovery_service.discover_companies(
            cities=request.cities,
            industries=request.industries,
            keywords=request.keywords,
            company_size=company_size_enum,
        )
        return {
            "message": "Job discovery successful",
            "companies": companies,
            "total_found": len(companies),
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
    if not request.company_ids:
        raise HTTPException(status_code=400, detail="company_ids is required")

    try:
        result = await extraction_service.extract_jobs_for_companies(
            db, request.company_ids
        )
        return ExtractResponse(
            results=result["results"],
            total_extracted=result["total_extracted"],
            total_new=result["total_new"],
            total_updated=result["total_updated"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/add",
    response_model=AddJobResponse,
    summary="Add a job by URL or pasted text",
    description=(
        "Add a job by URL (auto-scraped) or by pasted text. "
        "**URL scraping works best with direct company career pages** "
        "(e.g. company.com/careers/job/123). "
        "Aggregator sites like Indeed, Stepstone, and LinkedIn block automated access — "
        "for these, paste the job description text instead. "
        "You can provide both URL + text: the URL will be tried first, and text used as fallback."
    ),
)
async def add_job(
    request: AddJobRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    from urllib.parse import urlparse

    if not request.url and not request.raw_text:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of 'url' or 'raw_text'.",
        )

    job_opening: Optional[JobOpening] = None
    source_url: Optional[str] = request.url

    if request.url:
        parsed_url = urlparse(request.url)
        is_agg = _is_aggregator(parsed_url.hostname or "")

        if is_agg:
            if not request.raw_text:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"The site '{parsed_url.hostname}' is a job aggregator that blocks automated scraping. "
                        "Please paste the job description text in 'raw_text' and try again."
                    ),
                )
        else:
            try:
                scraped = await extraction_service.scrape_jobs(request.url)
                if scraped.jobs:
                    job_opening = scraped.jobs[0]
                else:
                    single_job = await extraction_service.scrape_single_job(request.url)
                    if single_job:
                        job_opening = single_job
            except Exception:
                pass

    if not job_opening and request.raw_text:
        try:
            job_opening = await extraction_service.extract_from_raw_text(
                request.raw_text, source_url=request.url
            )
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to extract job from text: {e}"
            )

    if not job_opening:
        if request.url and not request.raw_text:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Could not extract any jobs from the provided URL. "
                    "Try pasting the job description text in 'raw_text' instead."
                ),
            )
        raise HTTPException(status_code=502, detail="Could not extract any job data.")

    if not job_opening.application_url:
        if source_url:
            job_opening.application_url = source_url
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", job_opening.job_title.lower()).strip("-")
            job_opening.application_url = f"manual://{slug}"

    existing_job = (
        db.query(Job).filter(Job.source_url == job_opening.application_url).first()
    )

    if existing_job:
        existing_job.last_seen_at = _get_utc_now()
        existing_job.is_active = True
        if job_opening.description:
            existing_job.description = job_opening.description
        db.commit()
        db.refresh(existing_job)

        return AddJobResponse(
            job_id=existing_job.id,
            title=existing_job.title,
            company_name=existing_job.company.name
            if existing_job.company
            else "Unknown",
            company_id=existing_job.company_id,
            location=existing_job.location_city,
            description=existing_job.description or "",
            source=existing_job.source,
            is_new=False,
        )

    company_name = (
        job_opening.company_name
        or (urlparse(request.url).hostname if request.url else None)
        or "Unknown"
    )

    existing_company = (
        db.query(CompanyModel).filter(CompanyModel.name == company_name).first()
    )
    if existing_company:
        company = existing_company
    else:
        company = CompanyModel(
            name=company_name,
            url=request.url or "",
            url_verified=False,
        )
        db.add(company)
        db.flush()

    embedding = generate_job_embedding(
        title=job_opening.job_title,
        description=job_opening.description or "",
        requirements={"requirements": job_opening.requirements or []},
    )

    now = _get_utc_now()
    new_job = Job(
        company_id=company.id,
        source_url=job_opening.application_url,
        title=job_opening.job_title,
        description=job_opening.description or "",
        extracted_requirements={"requirements": job_opening.requirements or []},
        embedding=embedding_to_json(embedding),
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
        source="manual_url" if request.url else "manual_text",
        sources=["manual_url" if request.url else "manual_text"],
        location_city=job_opening.location,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    return AddJobResponse(
        job_id=new_job.id,
        title=new_job.title,
        company_name=company.name,
        company_id=company.id,
        location=job_opening.location,
        description=new_job.description or "",
        source=new_job.source,
        is_new=True,
    )


@router.post("/match", response_model=MatchResponse)
async def match_jobs(
    request: MatchRequest = Body(...),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
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
