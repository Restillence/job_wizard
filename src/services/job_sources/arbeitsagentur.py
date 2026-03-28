from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings
from src.services.job_sources.base import BaseJobSource, NormalizedJob, SearchParams


class ArbeitsagenturSource(BaseJobSource):
    API_BASE = "https://api-conSTRUCTOR.arbeitsagentur.de"
    SEARCH_URL = f"{API_BASE}/jd/api/v4/jobsuche"

    @property
    def name(self) -> str:
        return "arbeitsagentur"

    @property
    def supported_countries(self) -> List[str]:
        return ["DE"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch(self, params: SearchParams) -> List[NormalizedJob]:
        headers = {
            "X-API-Key": settings.ARBEITSAGENTUR_API_KEY,
            "Accept": "application/json",
        }

        query_parts = []
        if params.query:
            query_parts.append(params.query)
        if params.keywords:
            query_parts.extend(params.keywords)
        search_text = " ".join(query_parts) if query_parts else "*"

        api_params: Dict[str, Any] = {
            "suchbegriff": search_text,
            "page": params.page,
            "size": params.per_page,
            "angebotsart": 1,
        }

        if params.city:
            api_params["wo"] = params.city

        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    self.SEARCH_URL, params=api_params, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"Arbeitsagentur API error: {e}")
            return []

        return self._parse_results(data)

    def _parse_results(self, data: Dict[str, Any]) -> List[NormalizedJob]:
        jobs: List[NormalizedJob] = []
        result_list = data.get("stellenangebote", [])
        if not result_list:
            return jobs

        for item in result_list:
            try:
                job = self._parse_single(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"Arbeitsagentur parse error: {e}")
                continue

        return jobs

    def _parse_single(self, item: Dict[str, Any]) -> Optional[NormalizedJob]:
        refnr = item.get("refnr", "")
        if not refnr:
            return None

        title = item.get("beruf", "") or item.get("titel", "")
        if not title:
            return None

        company_name = item.get("arbeitgeber", "") or ""
        if not company_name:
            return None

        location = item.get("arbeitsort", {}) or {}
        city = location.get("ort", "")
        region = location.get("region", "")
        country = location.get("land", "DE")

        description_parts = []
        if item.get("stellenbeschreibung"):
            description_parts.append(item["stellenbeschreibung"])
        if item.get("aufgaben"):
            description_parts.append(f"Aufgaben: {item['aufgaben']}")
        if item.get("anforderungen"):
            description_parts.append(f"Anforderungen: {item['anforderungen']}")
        description = "\n\n".join(description_parts) if description_parts else None

        posted_at = None
        if item.get("aktuelleVeroeffentlichungsdatum"):
            try:
                posted_at = datetime.fromisoformat(
                    item["aktuelleVeroeffentlichungsdatum"]
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        is_remote = False
        if item.get("homeOfficeMoglich"):
            is_remote = str(item["homeOfficeMoglich"]).lower() in ("true", "1", "ja")

        source_url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

        return NormalizedJob(
            title=title,
            company_name=company_name,
            source_url=source_url,
            source=self.name,
            source_id=refnr,
            description=description,
            location_city=city,
            location_region=region,
            location_country=country,
            remote=is_remote,
            job_types=self._parse_job_types(item),
            posted_at=posted_at,
            visa_sponsorship=None,
            raw_data=item,
        )

    @staticmethod
    def _parse_job_types(item: Dict[str, Any]) -> Optional[List[str]]:
        types: List[str] = []
        befristung = item.get("befristung", "")
        if befristung and "unbefristet" in str(befristung).lower():
            types.append("permanent")
        elif befristung:
            types.append("temporary")

        arbeitszeit = item.get("arbeitszeit", "")
        if arbeitszeit:
            az_lower = str(arbeitszeit).lower()
            if "teilzeit" in az_lower:
                types.append("part-time")
            if "vollzeit" in az_lower:
                types.append("full-time")

        return types if types else None
