import json
import re
from typing import Optional
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler
from src.services.crawl_utils import JOB_CRAWL_CONFIG, clean_markdown
from src.services.llm_utils import acall_llm

EXTRACTION_MODEL = "openai/glm-4.7-flash"


class ExtractedJobData(BaseModel):
    job_title: str
    company_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    requirements: list[str] = []
    salary_range: Optional[str] = None
    job_type: Optional[str] = None
    is_remote: bool = False


class ExtractionResult(BaseModel):
    jobs: list[ExtractedJobData]


async def scrape_jobs(url: str) -> ExtractionResult:
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, crawler_config=JOB_CRAWL_CONFIG)
            markdown_content = result.markdown

            if not markdown_content or not markdown_content.strip():
                return ExtractionResult(jobs=[])

            markdown_content = clean_markdown(markdown_content, max_chars=12000)

            prompt = f"""Extract job posting details from the following page content.
This is a specific job listing page (not a career portal with multiple jobs).

Return ONLY a valid JSON object matching this schema:
{{
  "jobs": [
    {{
      "job_title": "string",
      "company_name": "string or null",
      "location": "string or null",
      "description": "string - the full job description text",
      "requirements": ["list of key requirements/skills"],
      "salary_range": "string or null",
      "job_type": "Full-time/Part-time/Contract or null",
      "is_remote": true/false
    }}
  ]
}}

Rules:
- Extract the FULL description, not a summary
- Include all mentioned skills/requirements as separate items
- If company name is not mentioned, set to null
- If the page contains multiple job listings, extract all of them

Page content:
{markdown_content}"""

            raw = await acall_llm(
                [{"role": "user", "content": prompt}],
                model=EXTRACTION_MODEL,
                max_tokens=4096,
            )
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n|\n```$", "", raw)

            try:
                parsed = json.loads(raw)
                return ExtractionResult(**parsed)
            except Exception:
                return ExtractionResult(jobs=[])
    except Exception as e:
        print(f"Job extraction failed for {url}: {e}")
        return ExtractionResult(jobs=[])
