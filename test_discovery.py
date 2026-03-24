import asyncio
import httpx
from typing import List, Optional
from pydantic import BaseModel

# --- Models ---
class CompanyBase(BaseModel):
    name: str
    city: Optional[str] = None
    industry: Optional[str] = None

class Company(CompanyBase):
    id: str
    url: str
    url_verified: bool = False

class JobSearchResult(BaseModel):
    title: str
    snippet: str
    link: str

class ExtractedCompany(BaseModel):
    name: str
    predicted_url: str

# --- Constants & Configuration ---
MIN_RESULTS_THRESHOLD_BROAD = 50
MIN_RESULTS_THRESHOLD_SPECIFIC = 5
AGGREGATOR_DOMAINS = [
    "linkedin.com", "indeed.com", "glassdoor.com", 
    "stepstone.de", "xing.com"
]

# --- In-Memory Mock Database ---
MOCK_DB: List[Company] = [
    Company(
        id="1", 
        name="TechCorp", 
        city="Berlin", 
        industry="AI", 
        url="https://techcorp.com/careers", 
        url_verified=True
    ),
    Company(
        id="2", 
        name="MunichData", 
        city="Munich", 
        industry="Data Science", 
        url="https://munichdata.io/jobs", 
        url_verified=True
    ),
]

# --- Services ---
class JobDiscoveryService:
    def __init__(self):
        self.db = MOCK_DB.copy()
    
    def search_local(self, cities: List[str] = None, industries: List[str] = None) -> List[Company]:
        print(f"[Local DB] Searching for cities={cities}, industries={industries}")
        results = []
        for company in self.db:
            if cities and company.city not in cities: continue
            if industries and company.industry not in industries: continue
            results.append(company)
        return results

    def _get_threshold(self, has_filters: bool) -> int:
        return MIN_RESULTS_THRESHOLD_SPECIFIC if has_filters else MIN_RESULTS_THRESHOLD_BROAD

    def _build_search_query(self, query_terms: List[str]) -> str:
        base_query = " ".join(query_terms) + " careers"
        
        # 1. Aggregator Exclusion
        domain_exclusions = " ".join([f"-site:{domain}" for domain in AGGREGATOR_DOMAINS])
        
        # 2. Exclusion Prompting (Exclude existing companies)
        existing_names = [c.name for c in self.db]
        # Simulate standard search engine logic for exclusions
        name_exclusions = " ".join([f"-{name.replace(' ', '')}" for name in existing_names[:5]])
        
        return f"{base_query} {domain_exclusions} {name_exclusions}"

    async def _mock_search_api(self, query: str) -> List[JobSearchResult]:
        print(f"[Search API] Executing query: '{query}'")
        await asyncio.sleep(1) # Simulate network call
        return [
            JobSearchResult(
                title="Python Developer at DataWorks", 
                snippet="Hiring now in Munich...", 
                link="https://dataworks.de/jobs"
            ),
            JobSearchResult(
                title="AI Engineer - InnovateAI", 
                snippet="Join our Berlin team", 
                link="https://innovateai.com/careers"
            ),
            JobSearchResult(
                title="Fake Linkedin Job", 
                snippet="This should be filtered by query, but caught if it slips through", 
                link="https://www.linkedin.com/jobs/view/123"
            )
        ]

    async def _extract_and_predict(self, search_results: List[JobSearchResult]) -> List[ExtractedCompany]:
        print("[LLM] Step 1 & 2: Extracting companies and predicting URLs...")
        await asyncio.sleep(1) # Simulate LLM call latency
        
        extracted = []
        for res in search_results:
            # Filter aggregators (Fallback in case search API failed to exclude)
            if any(domain in res.link for domain in AGGREGATOR_DOMAINS):
                print(f"[Filter] Excluded aggregator result: {res.link}")
                continue
            
            # Simulated LLM logic based on title parsing
            if "DataWorks" in res.title:
                extracted.append(ExtractedCompany(name="DataWorks", predicted_url="https://dataworks.de/careers"))
            elif "InnovateAI" in res.title:
                extracted.append(ExtractedCompany(name="InnovateAI", predicted_url="https://innovateai.com/careers"))
                
        return extracted

    async def _validate_urls(self, companies: List[ExtractedCompany]) -> List[Company]:
        print("[Validator] Step 3: HEAD validating predicted URLs...")
        validated = []
        
        # In a real environment, we'd use async httpx requests:
        # async with httpx.AsyncClient() as client:
        #     response = await client.head(url)
        # Mocking this out to avoid real external requests in the PoC.
        for i, comp in enumerate(companies):
            print(f"  -> Validating {comp.predicted_url} ... 200 OK")
            new_comp = Company(
                id=f"new_{i}",
                name=comp.name,
                url=comp.predicted_url,
                url_verified=True # Assumed success for mock
            )
            validated.append(new_comp)
        return validated

    async def discover_jobs(self, cities: List[str] = None, industries: List[str] = None, keywords: List[str] = None):
        print("\n" + "="*60)
        print(f"Starting Job Discovery: Cities={cities}, Industries={industries}, Keywords={keywords}")
        print("="*60)
        
        has_filters = any([cities, industries, keywords])
        threshold = self._get_threshold(has_filters)
        
        # 1. Search Local
        local_results = self.search_local(cities, industries)
        print(f"[Logic] Found {len(local_results)} local results. Threshold is {threshold}.")
        
        if len(local_results) >= threshold:
            print("[Logic] Threshold met! Returning local results.")
            return local_results
            
        print("[Logic] Below threshold. Triggering API Fallback...")
        
        # 2. Build Query & Search
        query_terms = (cities or []) + (industries or []) + (keywords or [])
        query = self._build_search_query(query_terms)
        raw_results = await self._mock_search_api(query)
        
        # 3. Extract & Predict (Two-Step Extraction)
        extracted = await self._extract_and_predict(raw_results)
        
        # 4. Validate URLs
        validated_companies = await self._validate_urls(extracted)
        
        # 5. Save & Combine
        print(f"[DB] Saving {len(validated_companies)} new companies to database.")
        for comp in validated_companies:
            comp.city = cities[0] if cities else None
            comp.industry = industries[0] if industries else None
            self.db.append(comp)
            local_results.append(comp)
            
        print(f"\n[Result] Total companies available: {len(local_results)}")
        for c in local_results:
            print(f"  - {c.name} ({c.url}) [Verified: {c.url_verified}]")
            
        return local_results

async def main():
    service = JobDiscoveryService()
    
    # Scenario 1: Specific query, insufficient local DB -> Triggers Fallback
    await service.discover_jobs(cities=["Munich"], industries=["Data Science"])
    
    # Scenario 2: Broad query, local DB is larger now, but still below 50 -> Triggers Fallback
    await service.discover_jobs()
    
if __name__ == "__main__":
    asyncio.run(main())