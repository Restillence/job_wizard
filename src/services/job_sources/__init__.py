from typing import List, Optional
from src.services.job_sources.base import BaseJobSource, NormalizedJob, SearchParams
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.arbeitnow import ArbeitnowSource

_REGISTRY: list[BaseJobSource] = []


def _get_registry() -> list[BaseJobSource]:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = [
            ArbeitsagenturSource(),
            ArbeitnowSource(),
        ]
    return _REGISTRY


def get_sources(country: Optional[str] = None) -> list[BaseJobSource]:
    sources = _get_registry()
    if country:
        sources = [
            s
            for s in sources
            if country.upper() in [c.upper() for c in s.supported_countries]
        ]
    return sources


def search_all(params: SearchParams) -> List[NormalizedJob]:
    all_jobs: List[NormalizedJob] = []
    seen_hashes: set[str] = set()

    sources = get_sources(country=params.country)
    for source in sources:
        try:
            jobs = source.fetch(params)
            for job in jobs:
                if job.dedup_hash not in seen_hashes:
                    seen_hashes.add(job.dedup_hash)
                    all_jobs.append(job)
        except Exception as e:
            print(f"Source {source.name} failed: {e}")
            continue

    return all_jobs
