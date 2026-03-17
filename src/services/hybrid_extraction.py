import asyncio
import re
import json
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from litellm import completion
from crawl4ai import AsyncWebCrawler
import httpx
from sqlalchemy.orm import Session
from src.config import settings
from src.models import Job, Company
from src.services.embeddings import generate_job_embedding, embedding_to_json


def _run_async_safe(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class JobOpening(BaseModel):
    job_title: str
    application_url: str
    requirements: Optional[List[str]] = None
    description: Optional[str] = None


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
        "workday": r"workday\.com",
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

            api_url = (
                url.rstrip("/")
                + "/fs/searchPagination/318c8bb6f553100021d223d9780d30be/1"
            )

            with httpx.Client(timeout=15) as client:
                response = client.get(api_url)
                if response.status_code != 200:
                    return ScrapedJobs(jobs=[])

                data = response.json()
                jobs = []
                for job_data in data.get("body", {}).get("children", []):
                    title = job_data.get("title", "Unknown")
                    external_url = job_data.get("externalUrl", url)
                    jobs.append(
                        JobOpening(
                            job_title=title,
                            application_url=external_url,
                            requirements=[],
                            description=None,
                        )
                    )
                return ScrapedJobs(jobs=jobs)
        except Exception as e:
            print(f"Workday extraction failed: {e}")
            return ScrapedJobs(jobs=[])

    async def _crawl4ai_fallback(self, url: str) -> ScrapedJobs:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            markdown_content = result.markdown

            if len(markdown_content) > 15000:
                markdown_content = markdown_content[:15000]

            prompt = f"""
            Extract job titles and their application URLs from the following markdown text scraped from a career page.
            Also extract a brief list of requirements if available.
            
            Markdown Content:
            {markdown_content}
            
            Return ONLY a valid JSON object matching this schema:
            {{
              "jobs": [
                {{"job_title": "Software Engineer", "application_url": "https://...", "requirements": ["Python", "Docker"]}}
              ]
            }}
            Do not include markdown formatting like ```json.
            """

            response = completion(
                model="openai/glm-5",
                api_base=settings.ZAI_API_BASE,
                api_key=settings.ZAI_API_KEY,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            try:
                parsed_data = json.loads(raw_json)
                return ScrapedJobs.model_validate(parsed_data)
            except Exception:
                return ScrapedJobs(jobs=[])

    def scrape_jobs(self, url: str) -> ScrapedJobs:
        ats_type = self.check_ats_footprint(url)

        if ats_type == "personio":
            return self._extract_personio_jobs(url)
        elif ats_type == "greenhouse":
            return self._extract_greenhouse_jobs(url)
        elif ats_type == "workday":
            return self._extract_workday_jobs(url)
        else:
            try:
                return _run_async_safe(self._crawl4ai_fallback(url))
            except Exception:
                return ScrapedJobs(jobs=[])

    def upsert_jobs(
        self,
        db: Session,
        company: Company,
        scraped_jobs: ScrapedJobs,
    ) -> tuple[List[Job], int, int]:
        now = get_utc_now()
        newly_added = 0
        updated = 0
        jobs_list: List[Job] = []

        for job_opening in scraped_jobs.jobs:
            if not job_opening.application_url:
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
                )
                db.add(new_job)
                newly_added += 1
                jobs_list.append(new_job)

        if newly_added > 0 or updated > 0:
            db.commit()
            for job in jobs_list:
                db.refresh(job)

        return jobs_list, newly_added, updated

    def extract_and_save_jobs(
        self,
        db: Session,
        company: Company,
    ) -> ExtractionResult:
        scraped_jobs = self.scrape_jobs(company.url)
        jobs, newly_added, updated = self.upsert_jobs(db, company, scraped_jobs)

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

    def extract_jobs_for_companies(
        self,
        db: Session,
        company_ids: List[str],
    ) -> dict:
        results = []
        total_extracted = 0
        total_new = 0
        total_updated = 0

        for company_id in company_ids:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                continue

            result = self.extract_and_save_jobs(db, company)
            results.append(
                {
                    "company_id": company_id,
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
