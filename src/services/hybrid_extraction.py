import asyncio
import re
import json
from typing import List, Optional
from pydantic import BaseModel
from litellm import completion
from crawl4ai import AsyncWebCrawler
from src.config import settings

class JobOpening(BaseModel):
    job_title: str
    application_url: str
    requirements: Optional[List[str]] = None
    description: Optional[str] = None

class ScrapedJobs(BaseModel):
    jobs: List[JobOpening]

class HybridExtractionService:
    def check_ats_footprint(self, url: str) -> bool:
        ats_patterns = [
            r"personio\.(de|com)",
            r"greenhouse\.io",
            r"workday\.com",
            r"index\.php\?ac=jobad",
        ]
        for pattern in ats_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

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
        if self.check_ats_footprint(url):
            # Fast path stub - normally HTTPX here
            return ScrapedJobs(jobs=[JobOpening(job_title="Software Engineer (ATS)", application_url=url, requirements=["ATS Check passed"])])
        else:
            return asyncio.run(self._crawl4ai_fallback(url))
