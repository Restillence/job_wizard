from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.database import get_db
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService
from src.models import CompanySize

router = APIRouter(prefix="/users", tags=["users"])
discovery_service = JobDiscoveryService()


class SavedSearchResponse(BaseModel):
    id: str
    cities: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    company_size: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "uuid",
                "cities": ["Berlin", "Munich"],
                "industries": ["AI"],
                "keywords": ["Python"],
                "company_size": "startup",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }
    }


class ReuseSearchResponse(BaseModel):
    search_id: str
    companies: List[dict]
    total_found: int
    newly_added: int
    source: str


@router.get("/{user_id}/searches", response_model=List[SavedSearchResponse])
async def get_user_searches(
    user_id: str,
    limit: int = Query(5, ge=1, le=10, description="Number of searches to return"),
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Get user's saved searches for auto-suggest.

    - Returns up to 5 most recent searches
    - Ordered by most recent first
    """
    if user_info.get("user_id") != user_id:
        raise HTTPException(
            status_code=403, detail="Cannot access other users' searches"
        )

    searches = discovery_service.get_user_searches(db, user_id, limit)

    return [SavedSearchResponse(**s) for s in searches]


@router.post(
    "/{user_id}/searches/{search_id}/reuse", response_model=ReuseSearchResponse
)
async def reuse_search(
    user_id: str,
    search_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Re-execute a saved search.

    - Finds the saved search by ID
    - Executes the same search query
    - Returns fresh results
    """
    if user_info.get("user_id") != user_id:
        raise HTTPException(
            status_code=403, detail="Cannot access other users' searches"
        )

    from src.models import UserSearch

    search = (
        db.query(UserSearch)
        .filter(
            UserSearch.id == search_id,
            UserSearch.user_id == user_id,
        )
        .first()
    )

    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")

    company_size_enum = None
    if search.company_size:
        try:
            company_size_enum = CompanySize(search.company_size)
        except ValueError:
            pass

    result = discovery_service.search_companies(
        db=db,
        user_id=user_id,
        cities=search.cities,
        industries=search.industries,
        keywords=search.keywords,
        company_size=company_size_enum,
    )

    return ReuseSearchResponse(
        search_id=search_id,
        companies=result.companies,
        total_found=result.total_found,
        newly_added=result.newly_added,
        source=result.source,
    )


@router.delete("/{user_id}/searches/{search_id}")
async def delete_search(
    user_id: str,
    search_id: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit),
):
    """
    Delete a saved search.
    """
    if user_info.get("user_id") != user_id:
        raise HTTPException(
            status_code=403, detail="Cannot access other users' searches"
        )

    from src.models import UserSearch

    search = (
        db.query(UserSearch)
        .filter(
            UserSearch.id == search_id,
            UserSearch.user_id == user_id,
        )
        .first()
    )

    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")

    db.delete(search)
    db.commit()

    return {"message": "Search deleted", "search_id": search_id}
