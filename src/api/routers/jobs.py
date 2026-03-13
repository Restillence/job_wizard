from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from src.database import get_db
from sqlalchemy.orm import Session
from src.api.deps import verify_jwt, check_rate_limit
from src.services.job_discovery import JobDiscoveryService, Company

router = APIRouter(prefix="/jobs", tags=["jobs"])
discovery_service = JobDiscoveryService()

class DiscoverQuery(BaseModel):
    query: str

class DiscoverResponse(BaseModel):
    message: str
    query: str
    companies: List[Company]

@router.post("/discover", response_model=DiscoverResponse)
async def discover_jobs(
    query: DiscoverQuery,
    db: Session = Depends(get_db),
    user_info: dict = Depends(verify_jwt),
    _rate_limit: bool = Depends(check_rate_limit)
):
    try:
        companies = discovery_service.discover_companies(query.query)
        return {
            "message": "Job discovery successful",
            "query": query.query,
            "companies": companies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
