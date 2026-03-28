from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.services.job_sources.base import BaseJobSource, NormalizedJob, SearchParams


class ArbeitnowSource(BaseJobSource):
    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    @property
    def name(self) -> str:
        return "arbeitnow"

    @property
    def supported_countries(self) -> List[str]:
        return ["DE", "AT", "CH"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch(self, params: SearchParams) -> List[NormalizedJob]:
        query_parts: List[str] = []
        if params.query:
            query_parts.append(params.query)
        if params.keywords:
            query_parts.extend(params.keywords)
        search_text = " ".join(query_parts) if query_parts else ""

        api_params: Dict[str, Any] = {
            "page": params.page,
            "per_page": params.per_page,
        }

        if search_text:
            api_params["search"] = search_text
        if params.city:
            api_params["location"] = params.city
        if params.country:
            api_params["country"] = params.country

        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(self.API_URL, params=api_params)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"Arbeitnow API error: {e}")
            return []

        return self._parse_results(data, params)

    def _parse_results(
        self, data: Dict[str, Any], params: SearchParams
    ) -> List[NormalizedJob]:
        jobs: List[NormalizedJob] = []
        raw_jobs = data.get("data", [])
        if not raw_jobs:
            return jobs

        for item in raw_jobs:
            try:
                job = self._parse_single(item, params)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"Arbeitnow parse error: {e}")
                continue

        return jobs

    def _parse_single(
        self, item: Dict[str, Any], params: SearchParams
    ) -> Optional[NormalizedJob]:
        slug = item.get("slug", "")
        source_url = item.get("url", "")
        if not source_url and slug:
            source_url = f"https://www.arbeitnow.com/jobs/{slug}"
        if not source_url:
            return None

        title = item.get("title", "")
        if not title:
            return None

        company_name = item.get("company_name", "")
        if not company_name:
            return None

        city = item.get("location", "") or ""
        country_code = item.get("country_code", params.country) or params.country

        description = item.get("description", "")

        posted_at = None
        if item.get("created_at"):
            try:
                created = item["created_at"]
                if isinstance(created, (int, float)):
                    posted_at = datetime.fromtimestamp(created, tz=timezone.utc)
                else:
                    posted_at = datetime.fromisoformat(
                        str(created).replace("Z", "+00:00")
                    )
            except (ValueError, TypeError, OSError):
                pass

        is_remote = bool(item.get("remote", False))

        salary_min = None
        salary_max = None
        salary_str = item.get("salary", "")
        if salary_str and isinstance(salary_str, str):
            salary_min, salary_max = self._parse_salary(salary_str)

        tags = item.get("tags", [])
        if tags and isinstance(tags, str):
            tags = [tags]

        return NormalizedJob(
            title=title,
            company_name=company_name,
            source_url=source_url,
            source=self.name,
            source_id=slug or None,
            description=description or None,
            location_city=city,
            location_country=country_code,
            remote=is_remote,
            job_types=self._parse_job_types(item),
            salary_min=salary_min,
            salary_max=salary_max,
            posted_at=posted_at,
            tags=tags if tags else None,
            visa_sponsorship=item.get("visa_sponsorship"),
            raw_data=item,
        )

    @staticmethod
    def _parse_salary(salary_str: str) -> tuple[Optional[float], Optional[float]]:
        import re as _re

        numbers = _re.findall(r"[\d]+(?:\.[\d]+)?", salary_str.replace(",", "."))
        if len(numbers) >= 2:
            return float(numbers[0]), float(numbers[1])
        elif len(numbers) == 1:
            return float(numbers[0]), None
        return None, None

    @staticmethod
    def _parse_job_types(item: Dict[str, Any]) -> Optional[List[str]]:
        types: List[str] = []
        if item.get("remote"):
            types.append("remote")
        job_type = str(item.get("job_type", "")).lower()
        if "full" in job_type:
            types.append("full-time")
        if "part" in job_type:
            types.append("part-time")
        if "contract" in job_type:
            types.append("contract")
        if "intern" in job_type:
            types.append("internship")
        return types if types else None
