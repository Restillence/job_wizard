from typing import Tuple
from sqlalchemy.orm import Session
from src.models import Company
from src.services.job_sources.base import NormalizedJob


def _generate_company_url(name: str) -> str:
    slug = name.lower().replace(" ", "-").replace(",", "")
    return f"https://{slug}.job-board-source.example.com"


def resolve_or_create_company(
    db: Session,
    job: NormalizedJob,
) -> Tuple[Company, bool]:
    company_name = job.company_name.strip()
    if not company_name:
        company_name = "Unknown Company"

    existing = db.query(Company).filter(Company.name == company_name).first()
    if existing:
        return existing, False

    url = _generate_company_url(company_name)

    existing_by_url = db.query(Company).filter(Company.url == url).first()
    if existing_by_url:
        return existing_by_url, False

    company = Company(
        name=company_name,
        url=url,
        city=job.location_city,
        url_verified=False,
    )
    db.add(company)
    db.flush()

    return company, True
