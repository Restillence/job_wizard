import json
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.services.job_sources.base import BaseJobSource, NormalizedJob, SearchParams

_API_KEY = "jobboerse-jobsuche"
_USER_AGENT = (
    "Jobsuche/2.9.2 (de.arbeitsagentur.jobboerse; build:1077;"
    " iOS 15.1.0) Alamofire/5.4.4"
)


class ArbeitsagenturSource(BaseJobSource):
    API_BASE = "https://rest.arbeitsagentur.de"
    SEARCH_URL = f"{API_BASE}/jobboerse/jobsuche-service/pc/v4/app/jobs"
    DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
    _ANGELOTSARTEN = [1, 4, 34]

    @property
    def name(self) -> str:
        return "arbeitsagentur"

    @property
    def supported_countries(self) -> List[str]:
        return ["DE"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def fetch(self, params: SearchParams) -> List[NormalizedJob]:
        headers = {
            "X-API-Key": _API_KEY,
            "User-Agent": _USER_AGENT,
            "Host": "rest.arbeitsagentur.de",
            "Accept": "application/json",
        }

        query_parts: List[str] = []
        if params.query:
            query_parts.append(params.query)
        if params.keywords:
            query_parts.extend(params.keywords)

        base_params: Dict[str, Any] = {
            "page": params.page,
            "size": params.per_page,
            "pav": "false",
        }

        if query_parts:
            base_params["was"] = " ".join(query_parts)
        if params.city:
            base_params["wo"] = params.city

        all_jobs: List[NormalizedJob] = []
        seen_refnrs: set = set()

        try:
            with httpx.Client(timeout=20, verify=False) as client:
                for angebotsart in self._ANGELOTSARTEN:
                    api_params = {**base_params, "angebotsart": angebotsart}
                    try:
                        response = client.get(
                            self.SEARCH_URL, params=api_params, headers=headers
                        )
                        response.raise_for_status()
                        data = response.json()
                    except Exception as e:
                        print(
                            f"Arbeitsagentur API error (angebotsart={angebotsart}): {e}"
                        )
                        continue

                    for job in self._parse_results(data):
                        if job.source_id not in seen_refnrs:
                            seen_refnrs.add(job.source_id)
                            all_jobs.append(job)
        except Exception as e:
            print(f"Arbeitsagentur API error: {e}")

        all_jobs.sort(
            key=lambda j: j.posted_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return all_jobs[: params.per_page]

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

        title = item.get("titel", "") or item.get("beruf", "")
        if not title:
            return None

        company_name = item.get("arbeitgeber", "") or ""
        if not company_name:
            return None

        location = item.get("arbeitsort", {}) or {}
        city = location.get("ort", "")
        region = location.get("region", "")
        country = location.get("land", "Deutschland")

        source_url = (
            item.get("externeUrl", "")
            or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
        )

        posted_at = None
        date_str = item.get("aktuelleVeroeffentlichungsdatum", "")
        if date_str:
            try:
                posted_at = datetime.fromisoformat(date_str).replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                pass

        return NormalizedJob(
            title=title,
            company_name=company_name,
            source_url=source_url,
            source=self.name,
            source_id=refnr,
            description=None,
            location_city=city,
            location_region=region,
            location_country=country,
            remote=False,
            job_types=None,
            posted_at=posted_at,
            visa_sponsorship=None,
            raw_data=item,
        )

    def fetch_detail(self, refnr: str) -> Optional[Dict[str, Any]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html",
            "Accept-Language": "de-DE,de;q=0.9",
        }
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(self.DETAIL_URL.format(refnr=refnr), headers=headers)
            if r.status_code != 200:
                return None
            return self._extract_jobdetail_json(r.text)

    def _extract_jobdetail_json(self, html: str) -> Optional[Dict[str, Any]]:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script in scripts:
            if "jobdetail" not in script:
                continue
            try:
                start = script.index("{")
                end = script.rindex("}") + 1
                data = json.loads(script[start:end])
                if "jobdetail" in data:
                    return data["jobdetail"]
            except (ValueError, json.JSONDecodeError):
                continue
        return None

    def enrich_jobs(self, jobs: List[NormalizedJob]) -> List[NormalizedJob]:
        for job in jobs:
            if not job.source_id:
                continue
            detail = self.fetch_detail(job.source_id)
            if not detail:
                continue
            desc = detail.get("stellenangebotsBeschreibung", "")
            if desc and (not job.description or len(desc) > len(job.description)):
                job.description = desc
            if detail.get("homeofficemoeglich") and not job.remote:
                job.remote = True
            time.sleep(0.2)
        return jobs
