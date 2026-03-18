from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService, CompanySearchResult
from src.models import CompanySize, Company as CompanyModel

router = APIRouter(prefix="/companies", tags=["companies"])
discovery_service = JobDiscoveryService()


class CompanyInResponse(BaseModel):
    id: str
    name: str
    city: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    url: str
    url_verified: bool = False


class CompanySearchResponse(BaseModel):
    companies: List[CompanyInResponse]
    total_found: int
    newly_added: int
    source: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "companies": [
                    {
                        "id": "uuid",
                        "name": "TechCorp",
                        "city": "Berlin",
                        "industry": "Software",
                        "company_size": "startup",
                        "url": "https://techcorp.example.com/careers",
                        "url_verified": True,
                    }
                ],
                "total_found": 15,
                "newly_added": 3,
                "source": "api_fallback",
            }
        }
    }


class ResolveUrlResponse(BaseModel):
    company_id: str
    company_name: str
    old_url: Optional[str]
    new_url: Optional[str]
    resolved: bool


@router.get("/search", response_model=CompanySearchResponse)
async def search_companies(
    cities: Optional[List[str]] = Query(
        None, description="Filter by cities (OR logic)"
    ),
    industries: Optional[List[str]] = Query(
        None, description="Filter by industries (OR logic)"
    ),
    keywords: Optional[List[str]] = Query(None, description="Keywords for search"),
    company_size: Optional[CompanySize] = Query(
        None, description="Filter by company size"
    ),
    user_id: Optional[str] = Query(
        None, description="User ID for saving search history"
    ),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Search for companies with self-building discovery.

    - Queries local DB first with fuzzy matching
    - If results below threshold, triggers API search with two-step extraction
    - New companies are saved to DB automatically
    - Search is saved to user history if user_id provided (max 5 per user)
    """
    result: CompanySearchResult = discovery_service.search_companies(
        db=db,
        user_id=user_id,
        cities=cities,
        industries=industries,
        keywords=keywords,
        company_size=company_size,
    )

    return CompanySearchResponse(
        companies=[CompanyInResponse(**c) for c in result.companies],
        total_found=result.total_found,
        newly_added=result.newly_added,
        source=result.source,
    )


@router.post("/{company_id}/resolve-url", response_model=ResolveUrlResponse)
async def resolve_company_url(
    company_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Lazy resolve career URL for a company with unverified URL.

    - Searches for the company's actual career page
    - Updates the database with the resolved URL
    - Returns the new URL if found
    """
    company = db.query(CompanyModel).filter(CompanyModel.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    old_url = company.url

    resolved_url = discovery_service.resolve_company_url_in_db(db, company_id)

    return ResolveUrlResponse(
        company_id=company_id,
        company_name=company.name,
        old_url=old_url,
        new_url=resolved_url,
        resolved=resolved_url is not None,
    )
