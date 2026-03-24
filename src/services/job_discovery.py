import json
import re
import asyncio
import concurrent.futures
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from duckduckgo_search import DDGS
from litellm import completion, acompletion
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.config import settings
from src.models import Company as CompanyModel, CompanySize, UserSearch


AGGREGATOR_DOMAINS = [
    "linkedin",
    "indeed",
    "glassdoor",
    "stepstone",
    "xing",
    "monster",
    "karriere",
    "stellenonline",
    "jobware",
    "stellenanzeigen",
]

MAX_CITIES = 5
MAX_INDUSTRIES = 5
MAX_KEYWORDS = 10
MAX_COMPANY_NAMES = 50


class Company(BaseModel):
    company_name: str
    career_url: str
    url_verified: bool = False
    city: Optional[str] = None
    industry: Optional[str] = None


class DiscoveryResult(BaseModel):
    companies: List[Company]


class CompanyNamesResult(BaseModel):
    companies: List[str]


class CompanySearchResult(BaseModel):
    companies: List[dict]
    total_found: int
    newly_added: int
    source: str


MIN_RESULTS_THRESHOLD_BROAD = 50
MIN_RESULTS_THRESHOLD_SPECIFIC = 5


class JobDiscoveryService:
    async def _search_tavily(
        self, client: httpx.AsyncClient, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.TAVILY_API_KEY:
            return None
        try:
            search_query = query
            if exclude_companies:
                exclusion_text = f" EXCLUDE: {', '.join(exclude_companies[:20])}"
                search_query = query + exclusion_text

            print(f"\n--- DEBUG: EXACT TAVILY SEARCH QUERY ---")
            print(search_query)
            print("----------------------------------------\n")

            data = {
                "query": search_query,
                "api_key": settings.TAVILY_API_KEY,
                "search_depth": "basic",
                "max_results": 20,
            }
            response = await client.post("https://api.tavily.com/search", json=data, timeout=15)
            if response.status_code == 200:
                res = response.json()
                print("\n--- DEBUG: RAW TAVILY JSON RESPONSE ---")
                print(json.dumps(res, indent=2)[:2000] + "\n... (truncated)")
                print("---------------------------------------\n")
                results = res.get("results", [])
                return [
                    {
                        "title": r.get("title"),
                        "href": r.get("url"),
                        "body": r.get("content"),
                    }
                    for r in results
                ]
        except Exception as e:
            print(f"Tavily failed: {e}")
        return None

    async def _search_serper(
        self, client: httpx.AsyncClient, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.SERPER_API_KEY:
            return None
        try:
            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            print(f"\n--- DEBUG: EXACT SERPER SEARCH QUERY ---")
            print(search_query)
            print("----------------------------------------\n")

            headers = {
                "X-API-KEY": settings.SERPER_API_KEY,
                "Content-Type": "application/json",
            }
            data = {"q": search_query, "num": 20}
            response = await client.post("https://google.serper.dev/search", headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                res = response.json()
                print("\n--- DEBUG: RAW SERPER JSON RESPONSE ---")
                print(json.dumps(res, indent=2)[:2000] + "\n... (truncated)")
                print("---------------------------------------\n")
                results = res.get("organic", [])
                return [
                    {
                        "title": r.get("title"),
                        "href": r.get("link"),
                        "body": r.get("snippet"),
                    }
                    for r in results
                ]
        except Exception as e:
            print(f"Serper failed: {e}")
        return None

    async def _search_brave(
        self, client: httpx.AsyncClient, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.BRAVE_API_KEY:
            return None
        try:
            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            print(f"Attempting Brave Search: {search_query[:80]}...")

            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": settings.BRAVE_API_KEY,
            }
            params = {"q": search_query}
            response = await client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                res = response.json()
                results = res.get("web", {}).get("results", [])
                return [
                    {
                        "title": r.get("title"),
                        "href": r.get("url"),
                        "body": r.get("description"),
                    }
                    for r in results
                ]
        except Exception as e:
            print(f"Brave failed: {e}")
        return None

    async def _search_ddg(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> List[dict]:
        try:
            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            print(f"Attempting DuckDuckGo Search (Fallback): {search_query[:80]}...")

            # DDGS is synchronous but we can run it in a thread
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=20))
            return list(results)
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    async def _execute_search(self, client: httpx.AsyncClient, query: str, exclude_companies: Optional[List[str]] = None) -> List[dict]:
        """Execute search using available APIs (first successful wins)."""
        results = await self._search_tavily(client, query, exclude_companies)
        if results: return results
        
        results = await self._search_serper(client, query, exclude_companies)
        if results: return results
        
        results = await self._search_brave(client, query, exclude_companies)
        if results: return results
        
        return await self._search_ddg(query, exclude_companies)

    def _build_search_query(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> str:
        """Build a search query targeting company career pages with aggregator exclusions."""
        city = cities[0] if cities else ""
        industry = industries[0] if industries else ""
        size = ""

        if company_size:
            size_map = {
                CompanySize.startup: "startup",
                CompanySize.hidden_champion: "mid-sized company",
                CompanySize.enterprise: "enterprise",
            }
            size = size_map.get(company_size, "")

        # 1. Mandate career-specific keywords in the title or text
        career_terms = '("open positions" OR "vacancies" OR "careers" OR "karriere" OR "stellenangebote")'
        # 2. Aggressively exclude job boards, news, blogs, and forums
        exclusions = '-site:linkedin.com -site:indeed.com -site:glassdoor.com -site:stepstone.de -site:xing.com -site:reddit.com -site:kununu.com -inurl:blog -inurl:news -inurl:press -inurl:article'
        
        city_str = f'"{city}"' if city else ""
        industry_str = f'"{industry}"' if industry else ""

        # 3. Combine with our parameters
        query = f'{city_str} {industry_str} {size} companies {career_terms} {exclusions}'.strip()
        query = " ".join(query.split())
        return query

    async def _execute_multi_query(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
        exclude_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute city-primary queries and merge results.
        Returns list of search results with their context (city/industry).
        """
        cities_list = (cities or [])[:MAX_CITIES]
        industries_list = (industries or [])[:MAX_INDUSTRIES]
        keywords_list = (keywords or [])[:MAX_KEYWORDS]

        all_results = []
        seen_urls = set()

        async with httpx.AsyncClient() as client:
            tasks = []
            
            if cities_list:
                for city in cities_list:
                    query = self._build_search_query(
                        cities=[city],
                        industries=industries_list,
                        keywords=keywords_list,
                        company_size=company_size,
                    )
                    tasks.append((query, {"city": city, "industry": industries_list[0] if industries_list else None}))
            elif industries_list:
                for industry in industries_list:
                    query = self._build_search_query(
                        cities=None,
                        industries=[industry],
                        keywords=keywords_list,
                        company_size=company_size,
                    )
                    tasks.append((query, {"city": None, "industry": industry}))
            else:
                query = self._build_search_query(
                    cities=None,
                    industries=None,
                    keywords=keywords_list,
                    company_size=company_size,
                )
                tasks.append((query, {"city": None, "industry": None}))

            # Run search queries in parallel
            search_jobs = [self._execute_search(client, t[0], exclude_companies) for t in tasks]
            results_batches = await asyncio.gather(*search_jobs)

            for i, batch in enumerate(results_batches):
                context = tasks[i][1]
                for r in batch:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r["context"] = context
                        all_results.append(r)

        return all_results

    def _is_aggregator_url(self, url: str) -> bool:
        """Check if URL belongs to a known job aggregator."""
        url_lower = url.lower()
        return any(agg in url_lower for agg in AGGREGATOR_DOMAINS)

    async def _extract_company_names(self, search_results: List[dict]) -> List[Dict[str, Any]]:
        """
        Use LLM to extract company names from search results.
        Returns list of dicts with company_name and context.
        """
        if not search_results:
            print("\n--- DEBUG: NO SEARCH RESULTS TO EXTRACT FROM ---")
            return []

        # We keep the context for each search result
        search_context = []
        for r in search_results[:30]:
            search_context.append({
                "title": r.get("title"),
                "url": r.get("href"),
                "snippet": r.get("body"),
                "context": r.get("context")
            })

        print(f"\n--- DEBUG: RAW SEARCH RESULTS (All {len(search_context)}) BEFORE LLM ---")
        print(json.dumps(search_context, indent=2))
        print("-------------------------------------------\n")

        prompt = f"""
You are an HR researcher. From these job search results, extract the COMPANY NAMES that are hiring.

IGNORE the job board websites themselves (LinkedIn, Indeed, Glassdoor, StepStone, XING, Monster, etc.).

Look for patterns like:
- "Senior Developer at [Company Name]"
- "[Company Name] is hiring"
- "Join [Company Name]"
- Company names in job titles

Return ONLY valid JSON with up to {MAX_COMPANY_NAMES} unique company names and their associated context index:
{{"results": [{{"name": "Company A", "context_index": 0}}, {{"name": "Company B", "context_index": 1}}]}}

Do not include markdown formatting. Just return the raw JSON string.

Search Results:
{json.dumps(search_context, indent=2)}
"""

        try:
            print(f"--- DEBUG: SENDING TO LLM TO EXTRACT NAMES ---")
            print(f"\n--- DEBUG: EXACT SYSTEM/USER PROMPT TO LLM (EXTRACT NAMES) ---")
            print(prompt)
            print("--------------------------------------------------------------\n")
            response = await acompletion(
                model="openai/glm-5",
                api_base=settings.ZAI_API_BASE,
                api_key=settings.ZAI_API_KEY,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()

            print("\n--- DEBUG: RAW LLM RESPONSE (NAMES) ---")
            print(raw_json)
            print("---------------------------------------\n")

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            parsed_data = json.loads(raw_json)
            extracted = []
            for item in parsed_data.get("results", []):
                name = item.get("name")
                idx = item.get("context_index")
                if name and idx is not None and idx < len(search_context):
                    extracted.append({
                        "name": name,
                        "context": search_context[idx]["context"]
                    })
            return extracted[:MAX_COMPANY_NAMES]
        except Exception as e:
            print(f"Failed to extract company names: {e}")
            return []

    async def _predict_career_urls(self, extracted_companies: List[Dict[str, Any]]) -> List[Company]:
        """
        Use LLM to batch predict career page URLs for company names.
        """
        if not extracted_companies:
            print("\n--- DEBUG: NO COMPANIES TO PREDICT URLS FOR ---")
            return []

        companies_data = []
        for item in extracted_companies:
            companies_data.append({
                "name": item["name"],
                "city": item["context"]["city"],
                "industry": item["context"]["industry"]
            })

        print(f"\n--- DEBUG: COMPANIES FOR URL PREDICTION (All {len(companies_data)}) BEFORE LLM ---")
        print(json.dumps(companies_data, indent=2))
        print("-------------------------------------------\n")

        prompt = f"""
You are an expert at finding company career pages. For each company, predict their most likely careers/jobs page URL.

Common patterns:
- careers.company.com or jobs.company.com
- company.com/careers or company.com/jobs
- company.com/en/careers

Return ONLY valid JSON:
{{
  "companies": [
    {{"company_name": "SAP", "career_url": "https://careers.sap.com", "city": "Walldorf", "industry": "Software"}},
    {{"company_name": "UnknownStartup", "career_url": "https://unknownstartup.com/careers", "city": "Berlin", "industry": "AI"}}
  ]
}}

Do not include markdown formatting. Just return the raw JSON string.

Companies:
{json.dumps(companies_data, indent=2)}
"""

        try:
            print(f"--- DEBUG: SENDING TO LLM TO PREDICT URLS ---")
            print(f"\n--- DEBUG: EXACT SYSTEM/USER PROMPT TO LLM (PREDICT URLS) ---")
            print(prompt)
            print("-------------------------------------------------------------\n")
            response = await acompletion(
                model="openai/glm-5",
                api_base=settings.ZAI_API_BASE,
                api_key=settings.ZAI_API_KEY,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()

            print("\n--- DEBUG: RAW LLM RESPONSE (URLS) ---")
            print(raw_json)
            print("--------------------------------------\n")

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            parsed_data = json.loads(raw_json)
            discovery = DiscoveryResult.model_validate(parsed_data)
            return discovery.companies
        except Exception as e:
            print(f"Failed to predict career URLs: {e}")
            return []

    async def _validate_url(self, client: httpx.AsyncClient, url: str) -> bool:
        """Quick HEAD request to check if URL is reachable, with GET fallback."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = await client.head(url, headers=headers, timeout=8, follow_redirects=True)
            if response.status_code == 200:
                return True
            if response.status_code in [403, 405]:
                # Some sites block HEAD or return 403 for it, try GET
                response = await client.get(url, headers=headers, timeout=8, follow_redirects=True)
                return response.status_code == 200
            return False
        except Exception:
            return False

    async def _validate_urls_parallel(self, companies: List[Company]) -> List[Company]:
        """
        Validate URLs with parallel HEAD requests using httpx.
        Mark verified=True for reachable URLs.
        """
        if not companies:
            return []

        async with httpx.AsyncClient() as client:
            tasks = [self._validate_url(client, c.career_url) for c in companies]
            validation_results = await asyncio.gather(*tasks)

            for i, is_valid in enumerate(validation_results):
                companies[i].url_verified = is_valid

        return companies

    def _dedupe_companies(self, companies: List[Company]) -> List[Company]:
        """Remove duplicate companies by URL or name."""
        seen_urls = set()
        seen_names = set()
        unique = []
        for c in companies:
            url_key = c.career_url.lower().rstrip("/")
            name_key = c.company_name.lower().strip()
            if url_key not in seen_urls and name_key not in seen_names:
                seen_urls.add(url_key)
                seen_names.add(name_key)
                unique.append(c)
        return unique

    async def discover_companies(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
        exclude_companies: Optional[List[str]] = None,
    ) -> List[Company]:
        """
        Main discovery flow (ASYNCHRONOUS):
        1. Execute city-primary search queries (parallel)
        2. Extract company names from results (handles aggregators)
        3. Predict career URLs for company names
        4. Validate URLs with HEAD requests (parallel)
        5. Dedupe and return
        """
        search_results = await self._execute_multi_query(
            cities=cities,
            industries=industries,
            keywords=keywords,
            company_size=company_size,
            exclude_companies=exclude_companies,
        )

        if not search_results:
            print("No search results found")
            return []

        extracted_companies = await self._extract_company_names(search_results)

        if exclude_companies:
            extracted_companies = [
                n
                for n in extracted_companies
                if n["name"].lower() not in [e.lower() for e in exclude_companies]
            ]

        if not extracted_companies:
            print("No company names extracted")
            return []

        print(f"Extracted {len(extracted_companies)} company names")

        companies = await self._predict_career_urls(extracted_companies)

        companies = await self._validate_urls_parallel(companies)

        companies = self._dedupe_companies(companies)

        print(
            f"Discovered {len(companies)} companies ({sum(1 for c in companies if c.url_verified)} verified)"
        )

        return companies

    async def resolve_career_url(self, company_name: str) -> Optional[str]:
        """
        Lazy resolution: search for a company's actual career page.
        Used when user selects a company with unverified URL.
        """
        query = f'"{company_name}" careers jobs hiring site'
        async with httpx.AsyncClient() as client:
            results = await self._execute_search(client, query)

            for r in results[:5]:
                url = r.get("href", "")
                if url and not self._is_aggregator_url(url):
                    if await self._validate_url(client, url):
                        return url

        return None

    def _search_local_db(
        self,
        db: Session,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> List[CompanyModel]:
        """Search local database with OR logic within each filter type."""
        query = db.query(CompanyModel)

        if cities:
            city_filters = [CompanyModel.city.ilike(f"%{city}%") for city in cities]
            query = query.filter(or_(*city_filters))

        if industries:
            industry_filters = [
                CompanyModel.industry.ilike(f"%{ind}%") for ind in industries
            ]
            query = query.filter(or_(*industry_filters))

        if keywords:
            keyword_filters = [
                or_(
                    CompanyModel.name.ilike(f"%{kw}%"),
                    CompanyModel.industry.ilike(f"%{kw}%"),
                    CompanyModel.city.ilike(f"%{kw}%"),
                    CompanyModel.industry.ilike(f"%{kw}%"),
                )
                for kw in keywords
            ]
            query = query.filter(or_(*keyword_filters))

        if company_size:
            query = query.filter(CompanyModel.company_size == company_size)

        return query.all()

    def _calculate_threshold(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> int:
        has_filters = any([cities, industries, keywords, company_size])
        return (
            MIN_RESULTS_THRESHOLD_SPECIFIC
            if has_filters
            else MIN_RESULTS_THRESHOLD_BROAD
        )

    def _save_companies_to_db(self, db: Session, companies: List[Company], company_size: Optional[CompanySize] = None) -> int:
        saved_count = 0
        for company in companies:
            existing = (
                db.query(CompanyModel)
                .filter(CompanyModel.url == company.career_url)
                .first()
            )

            if not existing:
                db_company = CompanyModel(
                    name=company.company_name,
                    url=company.career_url,
                    url_verified=company.url_verified,
                    city=company.city,
                    industry=company.industry,
                    company_size=company_size
                )
                db.add(db_company)
                saved_count += 1
            else:
                # Update metadata if missing
                if not existing.city and company.city:
                    existing.city = company.city
                if not existing.industry and company.industry:
                    existing.industry = company.industry
                if not existing.company_size and company_size:
                    existing.company_size = company_size
                if not existing.url_verified and company.url_verified:
                    existing.url_verified = True

        if saved_count > 0:
            db.commit()

        return saved_count

    def _save_user_search(
        self,
        db: Session,
        user_id: str,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> None:
        """Save search to user history, maintaining max 5 searches per user."""
        existing_searches = (
            db.query(UserSearch)
            .filter(UserSearch.user_id == user_id)
            .order_by(UserSearch.created_at.desc())
            .all()
        )

        search_data = {
            "cities": cities,
            "industries": industries,
            "keywords": keywords,
            "company_size": company_size.value if company_size else None,
        }

        for existing in existing_searches:
            if (
                existing.cities == search_data["cities"]
                and existing.industries == search_data["industries"]
                and existing.keywords == search_data["keywords"]
                and existing.company_size == search_data["company_size"]
            ):
                return

        if len(existing_searches) >= 5:
            oldest = (
                db.query(UserSearch)
                .filter(UserSearch.user_id == user_id)
                .order_by(UserSearch.created_at)
                .first()
            )
            if oldest:
                db.delete(oldest)

        new_search = UserSearch(
            user_id=user_id,
            cities=cities,
            industries=industries,
            keywords=keywords,
            company_size=company_size.value if company_size else None,
        )
        db.add(new_search)
        db.commit()

    async def search_companies(
        self,
        db: Session,
        user_id: Optional[str] = None,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> CompanySearchResult:
        """
        Search for companies with self-building discovery (ASYNCHRONOUS FALLBACK).

        1. Query local DB first
        2. If below threshold, trigger API discovery
        3. Save new companies to DB
        4. Save search to user history (if user_id provided)
        """
        local_companies = self._search_local_db(
            db, cities, industries, keywords, company_size
        )
        threshold = self._calculate_threshold(
            cities, industries, keywords, company_size
        )

        if len(local_companies) >= threshold:
            return CompanySearchResult(
                companies=[
                    {
                        "id": c.id,
                        "name": c.name,
                        "city": c.city,
                        "industry": c.industry,
                        "company_size": c.company_size.value
                        if c.company_size
                        else None,
                        "url": c.url,
                        "url_verified": c.url_verified,
                    }
                    for c in local_companies
                ],
                total_found=len(local_companies),
                newly_added=0,
                source="local",
            )

        # Get existing names for exclusion prompting
        existing_names = [c.name for c in db.query(CompanyModel.name).limit(20).all()]

        discovered = await self.discover_companies(
            cities=cities,
            industries=industries,
            keywords=keywords,
            company_size=company_size,
            exclude_companies=existing_names,
        )

        newly_added = self._save_companies_to_db(db, discovered, company_size)

        if user_id:
            self._save_user_search(
                db, user_id, cities, industries, keywords, company_size
            )

        all_companies = self._search_local_db(
            db, cities, industries, keywords, company_size
        )

        return CompanySearchResult(
            companies=[
                {
                    "id": c.id,
                    "name": c.name,
                    "city": c.city,
                    "industry": c.industry,
                    "company_size": c.company_size.value if c.company_size else None,
                    "url": c.url,
                    "url_verified": c.url_verified,
                }
                for c in all_companies
            ],
            total_found=len(all_companies),
            newly_added=newly_added,
            source="api_fallback" if newly_added > 0 else "local",
        )

    def get_user_searches(
        self, db: Session, user_id: str, limit: int = 5
    ) -> List[dict]:
        """Get user's saved searches, ordered by most recent."""
        searches = (
            db.query(UserSearch)
            .filter(UserSearch.user_id == user_id)
            .order_by(UserSearch.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": s.id,
                "cities": s.cities,
                "industries": s.industries,
                "keywords": s.keywords,
                "company_size": s.company_size,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in searches
        ]

    async def resolve_company_url_in_db(self, db: Session, company_id: str) -> Optional[str]:
        """
        Resolve and update career URL for a company in the database.
        Returns the resolved URL or None if resolution failed.
        """
        company = db.query(CompanyModel).filter(CompanyModel.id == company_id).first()
        if not company:
            return None

        resolved_url = await self.resolve_career_url(company.name)
        if resolved_url:
            company.url = resolved_url
            company.url_verified = True
            db.commit()
            return resolved_url

        return None
