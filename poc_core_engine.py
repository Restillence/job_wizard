import sys
import json
import asyncio
import re
from typing import List
from pydantic import BaseModel
from duckduckgo_search import DDGS
from litellm import completion
from crawl4ai import AsyncWebCrawler

# Fix Windows console encoding for Chinese characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ==========================================
# CONFIGURATION & API KEYS
# ==========================================
# Z.ai API Key - Get yours at https://open.bigmodel.cn/
ZAI_API_KEY = "10961f6dcd11491596cb665061971d99.VGiyR7D0E9Oo83hz"
ZAI_API_BASE = "https://api.z.ai/api/coding/paas/v4"
LLM_MODEL = "openai/glm-5"


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================
class Company(BaseModel):
    company_name: str
    career_url: str


class DiscoveryResult(BaseModel):
    companies: List[Company]


class JobOpening(BaseModel):
    job_title: str
    application_url: str


class ScrapedJobs(BaseModel):
    jobs: List[JobOpening]


# ==========================================
# LLM WRAPPER
# ==========================================
def llm_call(prompt: str) -> str:
    """Wrapper for LLM calls using Z.ai via OpenAI-compatible endpoint."""
    response = completion(
        model=LLM_MODEL,
        api_base=ZAI_API_BASE,
        api_key=ZAI_API_KEY,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ==========================================
# STEP 1: AGentic discovery
# ==========================================
def discover_companies(query: str) -> List[Company]:
    print(f"\n[*] Starting Agentic Discovery for query: '{query}'")

    # 1. Use DuckDuckGo Search (Free, no API key needed)
    print("    -> Querying DuckDuckGo Search...")
    search_results = DDGS().text(query, max_results=5)
    search_context = json.dumps(search_results, indent=2)

    # 2. Feed context to LLM for extraction
    print(f"    -> Asking LLM (Z.ai GLM-5) to extract top 2 companies and career URLs...")
    prompt = f"""
    You are an expert HR researcher. Based on the following search results, extract the top 2 software companies located in Frankfurt and their official career/jobs page URLs.
    
    Search Results:
    {search_context}
    
    Return ONLY a valid JSON object matching this schema exactly:
    {{
      "companies": [
        {{"company_name": "Name", "career_url": "https://..."}}
      ]
    }}
    Do not include markdown formatting like ```json. Just return the raw JSON string.
    """

    raw_json = llm_call(prompt)

    # Clean up markdown code blocks if the LLM ignores instructions
    if raw_json.startswith("```"):
        raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

    try:
        parsed_data = json.loads(raw_json)
        discovery = DiscoveryResult.model_validate(parsed_data)
        return discovery.companies
    except Exception as e:
        print(f"    [!] Failed to parse LLM response: {raw_json}")
        raise e


# ==========================================
# step 2: hybrid scraper (ats vs crawl4ai)
# ==========================================
def check_ats_footprint(url: str) -> bool:
    """Synchronous check for known ATS platforms in the URL."""
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


async def crawl4ai_fallback(url: str) -> ScrapedJobs:
    """Asynchronous wrapper for Crawl4AI to scrape unstructured pages."""
    print("    -> Initializing Crawl4AI for unstructured extraction...")
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        markdown_content = result.markdown

        # Keep context window manageable for the LLM
        if len(markdown_content) > 15000:
            markdown_content = markdown_content[:15000]

        print(f"    -> Crawl complete. Passing {len(markdown_content)} chars to LLM for parsing...")

        prompt = f"""
        Extract job titles and their application URLs from the following markdown text scraped from a career page.
        
        Markdown Content:
        {markdown_content}
        
        Return ONLY a valid JSON object matching this schema:
        {{
          "jobs": [
            {{"job_title": "Software Engineer", "application_url": "https://..."}}
          ]
        }}
        Do not include markdown formatting like ```json.
        """

        raw_json = llm_call(prompt)

        if raw_json.startswith("```"):
            raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

        try:
            parsed_data = json.loads(raw_json)
            return ScrapedJobs.model_validate(parsed_data)
        except Exception:
            print(f"    [!] Failed to parse Jobs LLM response: {raw_json}")
            return ScrapedJobs(jobs=[])


def hybrid_scrape(url: str) -> None:
    """Synchronous entry point for the Hybrid Scraper."""
    print(f"\n[*] Analyzing Target URL: {url}")

    if check_ats_footprint(url):
        print("    [SUCCESS] Fast Path ATS footprint detected!")
        print("    -> In production, we would use HTTPX to extract JSON/API payloads directly.")
    else:
        print("    [SLOW PATH] No known ATS found. Deploying Crawl4AI dynamic fallback...")
        # Await the async Crawl4AI process in our synchronous flow
        scraped_data = asyncio.run(crawl4ai_fallback(url))

        print("\n    [SUCCESS] AI Extraction Results:")
        for job in scraped_data.jobs:
            print(f"      - {job.job_title} ({job.application_url})")


# ==========================================
# main execution
# ==========================================
def main() -> None:
    print("=== JobWiz Core Engine PoC ===")

    # Phase 1: Agentic Discovery
    test_query = "Top 2 software companies in Frankfurt career pages"
    companies = discover_companies(test_query)

    print("\n[*] Discovery Results:")
    for c in companies:
        print(f"    - {c.company_name}: {c.career_url}")

    # Phase 2: Hybrid Extraction
    # We test both the discovered URLs and a hardcoded Personio URL to test the fast path
    urls_to_test = [c.career_url for c in companies]
    urls_to_test.append("https://jobs.personio.de/engineering")

    for url in urls_to_test:
        hybrid_scrape(url)

    print("\n=== PoC Execution Complete ===")


if __name__ == "__main__":
    main()
