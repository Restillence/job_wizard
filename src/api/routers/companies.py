from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService, CompanySearchResult
from src.models import CompanySize

router = APIRouter(prefix="/companies", tags=["companies"])
discovery_service = JobDiscoveryService()


class CompanySearchResponse(BaseModel):
    companies: List[dict]
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
                    }
                ],
                "total_found": 15,
                "newly_added": 3,
                "source": "api_fallback",
            }
        }
    }


@router.get("/search", response_model=CompanySearchResponse)
async def search_companies(
    city: Optional[str] = Query(None, description="Filter by city"),
    industry: Optional[str] = Query(None, description="Filter by industry"),
    keywords: Optional[str] = Query(None, description="Fuzzy search on company name"),
    company_size: Optional[CompanySize] = Query(
        None, description="Filter by company size"
    ),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Search for companies with self-building discovery.

    - Queries local DB first with fuzzy matching
    - If results below threshold, triggers API search with exclusion prompting
    - New companies are saved to DB automatically
    """
    result: CompanySearchResult = discovery_service.search_companies(
        db=db,
        city=city,
        industry=industry,
        keywords=keywords,
        company_size=company_size,
    )

    return CompanySearchResponse(
        companies=result.companies,
        total_found=result.total_found,
        newly_added=result.newly_added,
        source=result.source,
    )
