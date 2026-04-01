import asyncio
import os
import re
import sys
import json
from datetime import datetime, timezone
from typing import List, Optional

if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf-8"

from pydantic import BaseModel

from crawl4ai import AsyncWebCrawler  # type: ignore
from crawl4ai.async_configs import CrawlerRunConfig  # type: ignore
import httpx
from sqlalchemy.orm import Session
from src.config import settings
from src.models import Job, Company
from src.services.embeddings import generate_job_embedding, embedding_to_json
from src.services.llm_utils import call_llm

_JOB_LISTING_CONFIG = CrawlerRunConfig(
    word_count_threshold=10,
    excluded_tags=["nav", "footer", "header", "aside", "form", "noscript"],
    excluded_selector=".cookie-banner, .sidebar, .related-jobs, .recommendations, .similar-jobs, [role='navigation'], [role='banner'], [role='contentinfo']",
    remove_overlay_elements=True,
    remove_forms=True,
    only_text=True,
    exclude_external_links=True,
    exclude_social_media_links=True,
)

_SINGLE_JOB_CONFIG = CrawlerRunConfig(
    word_count_threshold=10,
    excluded_tags=["nav", "footer", "header", "aside", "form", "noscript"],
    excluded_selector=".cookie-banner, .sidebar, .related-jobs, .recommendations, .similar-jobs, [role='navigation'], [role='banner'], [role='contentinfo']",
    remove_overlay_elements=True,
    remove_forms=True,
    only_text=True,
    exclude_external_links=True,
    exclude_social_media_links=True,
)

_NOISE_PATTERNS = re.compile(
    r"(?mi)^.*\b(cookie|consent|privacy|datenschutz|impressum|newsletter|abonn|anmelden|registrier|sign[\s_-]?up|log[\s_-]?in|subscribe|newsletter|tracking|werbung|advertisement)\b.*$"
)
_IMG_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
_LINK_ONLY_PATTERN = re.compile(r"^\[([^\]]*)\]\([^\)]+\)$", re.MULTILINE)


def _clean_markdown(md: str, max_chars: int = 8000) -> str:
    md = _IMG_PATTERN.sub("", md)
    md = _LINK_ONLY_PATTERN.sub(r"\1", md)
    md = _NOISE_PATTERNS.sub("", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.strip()
    if len(md) > max_chars:
        md = md[:max_chars]
    return md


class JobOpening(BaseModel):
    job_title: str
    application_url: str
    company_name: Optional[str] = None
    requirements: Optional[List[str]] = None
    description: Optional[str] = None
    location: Optional[str] = None


class ScrapedJobs(BaseModel):
    jobs: List[JobOpening]


class ExtractionResult(BaseModel):
    jobs: List[dict]
    total_extracted: int
    newly_added: int
    updated: int


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HybridExtractionService:
    ATS_PATTERNS = {
        "personio": r"personio\.(de|com)",
        "greenhouse": r"greenhouse\.io",
        "workday": r"(my)?workday.*\.com",
        "generic": r"index\.php\?ac=jobad",
    }

    def check_ats_footprint(self, url: str) -> Optional[str]:
        for ats_name, pattern in self.ATS_PATTERNS.items():
            if re.search(pattern, url, re.IGNORECASE):
                return ats_name
        return None

    def _extract_personio_jobs(self, url: str) -> ScrapedJobs:
        try:
            company_id_match = re.search(r"personio\.(?:de|com)/([^/]+)", url)
            if not company_id_match:
                return ScrapedJobs(jobs=[])

            company_slug = company_id_match.group(1)
            api_url = f"https://{company_slug}.jobs.personio.de/api/v1/search-jobs"

            with httpx.Client(timeout=15) as client:
                response = client.get(api_url)
                if response.status_code != 200:
                    return ScrapedJobs(jobs=[])

                data = response.json()
                jobs = []
                for job_data in data.get("jobs", []):
                    jobs.append(
                        JobOpening(
                            job_title=job_data.get("name", "Unknown"),
                            application_url=f"https://{company_slug}.jobs.personio.de/job/{job_data.get('id')}",
                            requirements=job_data.get("keywords", []),
                            description=job_data.get("short_description"),
                            location=str(job_data.get("office", "")),
                        )
                    )
                return ScrapedJobs(jobs=jobs)
        except Exception as e:
            print(f"Personio extraction failed: {e}")
            return ScrapedJobs(jobs=[])

    def _extract_greenhouse_jobs(self, url: str) -> ScrapedJobs:
        try:
            board_token_match = re.search(r"greenhouse\.io/([^/]+)", url)
            if not board_token_match:
                return ScrapedJobs(jobs=[])

            board_token = board_token_match.group(1).split(".")[0]
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

            with httpx.Client(timeout=15) as client:
                response = client.get(api_url)
                if response.status_code != 200:
                    return ScrapedJobs(jobs=[])

                data = response.json()
                jobs = []
                for job_data in data.get("jobs", []):
                    jobs.append(
                        JobOpening(
                            job_title=job_data.get("title", "Unknown"),
                            application_url=f"https://boards.greenhouse.io/{board_token}/jobs/{job_data.get('id')}",
                            requirements=[],
                            description=None,
                            location=job_data.get("location", {}).get("name", ""),
                        )
                    )
                return ScrapedJobs(jobs=jobs)
        except Exception as e:
            print(f"Greenhouse extraction failed: {e}")
            return ScrapedJobs(jobs=[])

    def _extract_workday_jobs(self, url: str) -> ScrapedJobs:
        try:
            if "myworkdayjobs.com" not in url:
                return ScrapedJobs(jobs=[])

            base_url = url.rstrip("/")
            api_url = f"{base_url}/wfp/career/careersection/alljobs/search"

            with httpx.Client(timeout=15) as client:
                response = client.get(api_url)
                if response.status_code != 200:
                    return ScrapedJobs(jobs=[])

                data = response.json()
                jobs = []
                for job_data in data.get("body", {}).get("children", []):
                    title = job_data.get("title", "Unknown")
                    external_url = job_data.get("externalUrl", url)
                    location = job_data.get("locationsText", "")
                    jobs.append(
                        JobOpening(
                            job_title=title,
                            application_url=external_url,
                            requirements=[],
                            description=None,
                            location=location,
                        )
                    )
                return ScrapedJobs(jobs=jobs)
        except Exception as e:
            print(f"Workday extraction failed: {e}")
            return ScrapedJobs(jobs=[])

    async def _crawl4ai_fallback(self, url: str) -> ScrapedJobs:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, crawler_config=_JOB_LISTING_CONFIG)
            markdown_content = _clean_markdown(result.markdown, max_chars=12000)

            prompt = f"""
            Extract job postings from the following markdown text scraped from a career page.
            For each job, extract:
            - job_title: The job title
            - application_url: Direct URL to apply or view the job (use the original source URL if none found)
            - company_name: The name of the hiring company (NOT the job board domain)
            - requirements: List of required skills/qualifications
            - description: Full job description including responsibilities and qualifications
            - location: Job location (city, country)

            Markdown Content:
            {markdown_content}

            Return ONLY a valid JSON object matching this schema:
            {{
              "jobs": [
                {{"job_title": "Software Engineer", "application_url": "https://...", "company_name": "TechCorp", "requirements": ["Python", "Docker"], "description": "Full description...", "location": "Munich"}}
              ]
            }}
            Do not include markdown formatting like ```json.
            """

            try:
                raw_json = call_llm(
                    [{"role": "user", "content": prompt}], timeout=120, max_tokens=4096
                )
            except Exception as e:
                print(f"LLM call failed in _crawl4ai_fallback: {e}")
                return ScrapedJobs(jobs=[])

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            try:
                parsed_data = json.loads(raw_json)
                return ScrapedJobs.model_validate(parsed_data)
            except Exception:
                return ScrapedJobs(jobs=[])

    async def scrape_single_job(self, url: str) -> Optional[JobOpening]:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, crawler_config=_SINGLE_JOB_CONFIG)
            markdown_content = _clean_markdown(result.markdown, max_chars=8000)

            prompt = f"""
            Extract the full job posting details from the following page content.
            This is a SINGLE job posting page, not a job listing page.

            Extract ALL of the following:
            - job_title: The exact job title
            - application_url: The URL to apply (use the page URL if none found)
            - company_name: The name of the hiring company (NOT the job board domain like indeed.com)
            - requirements: Full list of required skills, qualifications, and experience
            - description: The COMPLETE job description including all responsibilities, tasks, qualifications, and benefits. Be thorough - include everything.
            - location: Full location (city, address if available)

            Page Content:
            {markdown_content}

            Return ONLY a valid JSON object matching this schema:
            {{
              "job_title": "Software Engineer",
              "application_url": "https://...",
              "company_name": "TechCorp",
              "requirements": ["Python", "Docker", "3+ years experience"],
              "description": "Full detailed description of the role including responsibilities, qualifications, benefits...",
              "location": "Berlin, Germany"
            }}
            If you cannot identify a job posting on this page, return null.
            Do not include markdown formatting like ```json.
            """

            try:
                raw_json = call_llm(
                    [{"role": "user", "content": prompt}], timeout=120, max_tokens=4096
                )
            except Exception as e:
                print(f"LLM call failed in scrape_single_job: {e}")
                return None

            if raw_json.lower() == "null" or not raw_json:
                return None

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            try:
                parsed_data = json.loads(raw_json)
                return JobOpening.model_validate(parsed_data)
            except Exception:
                return None

    async def extract_from_raw_text(
        self, raw_text: str, source_url: Optional[str] = None
    ) -> Optional[JobOpening]:
        prompt = f"""
        Extract the full job posting details from the following text, which was copied/pasted by a user from a job listing page.

        Extract ALL of the following:
        - job_title: The exact job title
        - company_name: The name of the hiring company (NOT the job board domain)
        - requirements: Full list of required skills, qualifications, and experience
        - description: The COMPLETE job description including all responsibilities, tasks, qualifications, and benefits. Be thorough - include everything.
        - location: Full location (city, country)

        Job Text:
        {raw_text}

        Return ONLY a valid JSON object matching this schema:
        {{
          "job_title": "Software Engineer",
          "company_name": "TechCorp",
          "requirements": ["Python", "Docker", "3+ years experience"],
          "description": "Full detailed description of the role including responsibilities, qualifications, benefits...",
          "location": "Berlin, Germany"
        }}
        If you cannot identify a job posting in this text, return null.
        Do not include markdown formatting like ```json.
        """

        try:
            raw_json = call_llm(
                [{"role": "user", "content": prompt}], timeout=120, max_tokens=4096
            )
        except Exception as e:
            print(f"LLM call failed in extract_from_raw_text: {e}")
            return None

        if raw_json.lower() == "null" or not raw_json:
            return None

        if raw_json.startswith("```"):
            raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

        try:
            parsed_data = json.loads(raw_json)
            job_opening = JobOpening.model_validate(parsed_data)
            if source_url:
                job_opening.application_url = source_url
            elif not job_opening.application_url:
                slug = re.sub(r"[^a-z0-9]+", "-", job_opening.job_title.lower()).strip(
                    "-"
                )
                job_opening.application_url = f"manual://{slug}"
            return job_opening
        except Exception:
            return None

    async def scrape_jobs(self, url: str) -> ScrapedJobs:
        ats_type = self.check_ats_footprint(url)

        if ats_type == "personio":
            return self._extract_personio_jobs(url)
        elif ats_type == "greenhouse":
            return self._extract_greenhouse_jobs(url)
        elif ats_type == "workday":
            return self._extract_workday_jobs(url)
        else:
            try:
                return await self._crawl4ai_fallback(url)
            except Exception:
                return ScrapedJobs(jobs=[])

    def upsert_jobs(
        self,
        db: Session,
        company: Company,
        scraped_jobs: ScrapedJobs,
        target_cities: Optional[List[str]] = None,
    ) -> tuple[List[Job], int, int]:
        now = get_utc_now()
        newly_added = 0
        updated = 0
        jobs_list: List[Job] = []

        for job_opening in scraped_jobs.jobs:
            if not job_opening.application_url:
                continue

            if target_cities:
                location_str = (job_opening.location or "").lower()
                title_str = job_opening.job_title.lower()
                # Accept if any target city is in location or title, or if location indicates remote
                valid_location = False
                for city in target_cities:
                    c_lower = city.lower()
                    if c_lower in location_str or c_lower in title_str:
                        valid_location = True
                        break
                if not valid_location and (
                    "remote" in location_str or "remote" in title_str
                ):
                    valid_location = True

                if not valid_location:
                    print(
                        f"Discarding job '{job_opening.job_title}' at '{job_opening.location}' - does not match target cities {target_cities}"
                    )
                    continue

            existing_job = (
                db.query(Job)
                .filter(Job.source_url == job_opening.application_url)
                .first()
            )

            if existing_job:
                existing_job.last_seen_at = now
                existing_job.is_active = True
                if job_opening.description:
                    existing_job.description = job_opening.description
                updated += 1
                jobs_list.append(existing_job)
            else:
                embedding = generate_job_embedding(
                    title=job_opening.job_title,
                    description=job_opening.description or "",
                    requirements={"requirements": job_opening.requirements or []},
                )

                new_job = Job(
                    company_id=company.id,
                    source_url=job_opening.application_url,
                    title=job_opening.job_title,
                    description=job_opening.description or "",
                    extracted_requirements={
                        "requirements": job_opening.requirements or []
                    },
                    embedding=embedding_to_json(embedding),
                    is_active=True,
                    first_seen_at=now,
                    last_seen_at=now,
                    source="company_scrape",
                    sources=["company_scrape"],
                )
                db.add(new_job)
                newly_added += 1
                jobs_list.append(new_job)

        if newly_added > 0 or updated > 0:
            db.commit()
            for job in jobs_list:
                db.refresh(job)

        return jobs_list, newly_added, updated

    async def extract_and_save_jobs(
        self,
        db: Session,
        company: Company,
        target_cities: Optional[List[str]] = None,
    ) -> ExtractionResult:
        scraped_jobs = await self.scrape_jobs(company.url)
        jobs, newly_added, updated = self.upsert_jobs(
            db, company, scraped_jobs, target_cities
        )

        return ExtractionResult(
            jobs=[
                {
                    "id": job.id,
                    "title": job.title,
                    "source_url": job.source_url,
                    "company_id": job.company_id,
                    "is_active": job.is_active,
                }
                for job in jobs
            ],
            total_extracted=len(jobs),
            newly_added=newly_added,
            updated=updated,
        )

    async def extract_jobs_for_companies(
        self,
        db: Session,
        company_ids: List[str],
        target_cities: Optional[List[str]] = None,
    ) -> dict:
        results = []
        total_extracted = 0
        total_new = 0
        total_updated = 0

        # Run extractions in parallel
        tasks = []
        companies = []
        for company_id in company_ids:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                companies.append(company)
                tasks.append(self.extract_and_save_jobs(db, company, target_cities))

        if not tasks:
            return {
                "results": [],
                "total_extracted": 0,
                "total_new": 0,
                "total_updated": 0,
            }

        extraction_results = await asyncio.gather(*tasks)

        for i, result in enumerate(extraction_results):
            company = companies[i]
            results.append(
                {
                    "company_id": company.id,
                    "company_name": company.name,
                    "jobs": result.jobs,
                    "newly_added": result.newly_added,
                    "updated": result.updated,
                }
            )
            total_extracted += result.total_extracted
            total_new += result.newly_added
            total_updated += result.updated

        return {
            "results": results,
            "total_extracted": total_extracted,
            "total_new": total_new,
            "total_updated": total_updated,
        }
