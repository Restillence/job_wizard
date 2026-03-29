from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.services.job_sources.dedup import compute_dedup_hash


class SearchParams(BaseModel):
    query: Optional[str] = None
    city: Optional[str] = None
    country: str = "DE"
    page: int = 1
    per_page: int = 25
    keywords: Optional[List[str]] = None


class NormalizedJob(BaseModel):
    title: str
    company_name: str
    source_url: str
    source: str
    source_id: Optional[str] = None
    description: Optional[str] = None
    location_city: Optional[str] = None
    location_region: Optional[str] = None
    location_country: Optional[str] = None
    remote: bool = False
    job_types: Optional[List[str]] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "EUR"
    posted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    visa_sponsorship: Optional[bool] = None
    raw_data: Optional[Dict[str, Any]] = None

    def model_post_init(self, __context: Any) -> None:
        pass

    @property
    def dedup_hash(self) -> str:
        return compute_dedup_hash(
            title=self.title,
            company_name=self.company_name,
            city=self.location_city or "",
        )


class BaseJobSource(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_countries(self) -> List[str]: ...

    @abstractmethod
    def fetch(self, params: SearchParams) -> List[NormalizedJob]: ...
