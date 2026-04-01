import json
import re
from typing import Optional
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig
from src.config import settings

_JOB_EXTRACTION_CONFIG = CrawlerRunConfig(
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
    r"(?mi)^.*\b(cookie|consent|privacy|datenschutz|impressum|newsletter|abonn|anmelden|registrier|sign[\s_-]?up|log[\s_-]?in|subscribe|tracking|werbung|advertisement)\b.*$"
)
_IMG_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
_LINK_ONLY_PATTERN = re.compile(r"^\[([^\]]*)\]\([^\)]+\)$", re.MULTILINE)


def _clean_markdown(md: str, max_chars: int = 12000) -> str:
    md = _IMG_PATTERN.sub("", md)
    md = _LINK_ONLY_PATTERN.sub(r"\1", md)
    md = _NOISE_PATTERNS.sub("", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.strip()
    if len(md) > max_chars:
        md = md[:max_chars]
    return md


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
            result = await crawler.arun(url=url, crawler_config=_JOB_EXTRACTION_CONFIG)
            markdown_content = result.markdown

            if not markdown_content or not markdown_content.strip():
                return ExtractionResult(jobs=[])

            markdown_content = _clean_markdown(markdown_content, max_chars=12000)

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

            from src.services.llm_utils import call_llm

            raw = call_llm([{"role": "user", "content": prompt}])
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
