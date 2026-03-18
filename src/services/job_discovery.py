import json
import re
import urllib.request
import urllib.parse
import concurrent.futures
from typing import List, Optional
from pydantic import BaseModel
from duckduckgo_search import DDGS
from litellm import completion
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
    def _search_tavily(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.TAVILY_API_KEY:
            return None
        try:
            print(f"Attempting Tavily Search: {query[:80]}...")

            search_query = query
            if exclude_companies:
                exclusion_text = f" EXCLUDE: {', '.join(exclude_companies[:20])}"
                search_query = query + exclusion_text

            url = "https://api.tavily.com/search"
            data = json.dumps(
                {
                    "query": search_query,
                    "api_key": settings.TAVILY_API_KEY,
                    "search_depth": "basic",
                    "max_results": 20,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res = json.loads(response.read())
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

    def _search_serper(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.SERPER_API_KEY:
            return None
        try:
            print(f"Attempting Serper (Google) Search: {query[:80]}...")

            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            url = "https://google.serper.dev/search"
            data = json.dumps({"q": search_query, "num": 20}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "X-API-KEY": settings.SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res = json.loads(response.read())
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

    def _search_brave(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> Optional[List[dict]]:
        if not settings.BRAVE_API_KEY:
            return None
        try:
            print(f"Attempting Brave Search: {query[:80]}...")

            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(search_query)}"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.BRAVE_API_KEY,
                },
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res = json.loads(response.read())
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

    def _search_ddg(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> List[dict]:
        try:
            print(f"Attempting DuckDuckGo Search (Fallback): {query[:80]}...")

            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            return DDGS().text(search_query, max_results=20)
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    def _execute_search(self, query: str) -> List[dict]:
        """Execute search using available APIs (first successful wins)."""
        return (
            self._search_tavily(query)
            or self._search_serper(query)
            or self._search_brave(query)
            or self._search_ddg(query)
        )

    def _build_search_query(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> str:
        """Build a search query targeting company career pages with aggregator exclusions."""
        parts = []

        if cities:
            parts.extend(cities)
        if industries:
            parts.extend(industries)
        if keywords:
            parts.extend(keywords)
        if company_size:
            size_map = {
                CompanySize.startup: "startup",
                CompanySize.hidden_champion: "mid-sized company",
                CompanySize.enterprise: "enterprise",
            }
            parts.append(size_map.get(company_size, ""))

        parts.append("companies careers hiring")

        exclusions = " ".join(f"-{d}" for d in AGGREGATOR_DOMAINS)

        return f"{' '.join(parts)} {exclusions}".strip()

    def _execute_multi_query(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> List[dict]:
        """
        Execute city-primary queries and merge results.
        If no cities, use industries as primary. If neither, single query.
        """
        cities = (cities or [])[:MAX_CITIES]
        industries = (industries or [])[:MAX_INDUSTRIES]
        keywords = (keywords or [])[:MAX_KEYWORDS]

        all_results = []
        seen_urls = set()

        if cities:
            for city in cities:
                query = self._build_search_query(
                    cities=[city],
                    industries=industries,
                    keywords=keywords,
                    company_size=company_size,
                )
                results = self._execute_search(query)
                for r in results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
        elif industries:
            for industry in industries:
                query = self._build_search_query(
                    cities=None,
                    industries=[industry],
                    keywords=keywords,
                    company_size=company_size,
                )
                results = self._execute_search(query)
                for r in results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
        else:
            query = self._build_search_query(
                cities=None,
                industries=None,
                keywords=keywords,
                company_size=company_size,
            )
            all_results = self._execute_search(query)

        return all_results

    def _is_aggregator_url(self, url: str) -> bool:
        """Check if URL belongs to a known job aggregator."""
        url_lower = url.lower()
        return any(agg in url_lower for agg in AGGREGATOR_DOMAINS)

    def _extract_company_names(self, search_results: List[dict]) -> List[str]:
        """
        Use LLM to extract company names from search results.
        Handles results from job aggregators by extracting company names from job listings.
        """
        if not search_results:
            return []

        search_context = json.dumps(search_results[:30], indent=2)

        prompt = f"""
You are an HR researcher. From these job search results, extract the COMPANY NAMES that are hiring.

IGNORE the job board websites themselves (LinkedIn, Indeed, Glassdoor, StepStone, XING, Monster, etc.).

Look for patterns like:
- "Senior Developer at [Company Name]"
- "[Company Name] is hiring"
- "Join [Company Name]"
- Company names in job titles

Return ONLY valid JSON with up to {MAX_COMPANY_NAMES} unique company names:
{{"companies": ["Company A", "Company B", "Company C"]}}

Do not include markdown formatting. Just return the raw JSON string.

Search Results:
{search_context}
"""

        try:
            response = completion(
                model="openai/glm-5",
                api_base=settings.ZAI_API_BASE,
                api_key=settings.ZAI_API_KEY,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            parsed_data = json.loads(raw_json)
            result = CompanyNamesResult.model_validate(parsed_data)
            return result.companies[:MAX_COMPANY_NAMES]
        except Exception as e:
            print(f"Failed to extract company names: {e}")
            return []

    def _predict_career_urls(self, company_names: List[str]) -> List[Company]:
        """
        Use LLM to batch predict career page URLs for company names.
        """
        if not company_names:
            return []

        companies_json = json.dumps(company_names, indent=2)

        prompt = f"""
You are an expert at finding company career pages. For each company, predict their most likely careers/jobs page URL.

Common patterns:
- careers.company.com or jobs.company.com
- company.com/careers or company.com/jobs
- company.com/en/careers

For unknown companies, make a reasonable guess based on the company name.

Return ONLY valid JSON:
{{
  "companies": [
    {{"company_name": "SAP", "career_url": "https://careers.sap.com"}},
    {{"company_name": "UnknownStartup", "career_url": "https://unknownstartup.com/careers"}}
  ]
}}

Do not include markdown formatting. Just return the raw JSON string.

Companies:
{companies_json}
"""

        try:
            response = completion(
                model="openai/glm-5",
                api_base=settings.ZAI_API_BASE,
                api_key=settings.ZAI_API_KEY,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()

            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

            parsed_data = json.loads(raw_json)
            discovery = DiscoveryResult.model_validate(parsed_data)
            return discovery.companies
        except Exception as e:
            print(f"Failed to predict career URLs: {e}")
            return []

    def _validate_url(self, url: str) -> bool:
        """Quick HEAD request to check if URL is reachable."""
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0 (compatible; JobWiz/1.0)")
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def _validate_urls_parallel(self, companies: List[Company]) -> List[Company]:
        """
        Validate URLs with parallel HEAD requests.
        Mark verified=True for reachable URLs.
        """
        if not companies:
            return []

        def check_company(company: Company) -> Company:
            if company.career_url:
                company.url_verified = self._validate_url(company.career_url)
            return company

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(check_company, companies))

        return results

    def _dedupe_companies(self, companies: List[Company]) -> List[Company]:
        """Remove duplicate companies by URL."""
        seen = set()
        unique = []
        for c in companies:
            url_key = c.career_url.lower().rstrip("/")
            if url_key not in seen:
                seen.add(url_key)
                unique.append(c)
        return unique

    def discover_companies(
        self,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
        exclude_companies: Optional[List[str]] = None,
    ) -> List[Company]:
        """
        Main discovery flow:
        1. Execute city-primary search queries
        2. Extract company names from results (handles aggregators)
        3. Predict career URLs for company names
        4. Validate URLs with HEAD requests
        5. Dedupe and return
        """
        search_results = self._execute_multi_query(
            cities=cities,
            industries=industries,
            keywords=keywords,
            company_size=company_size,
        )

        if not search_results:
            print("No search results found")
            return []

        company_names = self._extract_company_names(search_results)

        if exclude_companies:
            company_names = [
                n
                for n in company_names
                if n.lower() not in [e.lower() for e in exclude_companies]
            ]

        if not company_names:
            print("No company names extracted")
            return []

        print(f"Extracted {len(company_names)} company names")

        companies = self._predict_career_urls(company_names)

        companies = self._validate_urls_parallel(companies)

        companies = self._dedupe_companies(companies)

        print(
            f"Discovered {len(companies)} companies ({sum(1 for c in companies if c.url_verified)} verified)"
        )

        return companies

    def resolve_career_url(self, company_name: str) -> Optional[str]:
        """
        Lazy resolution: search for a company's actual career page.
        Used when user selects a company with unverified URL.
        """
        query = f'"{company_name}" careers jobs hiring site'
        results = self._execute_search(query)

        for r in results[:5]:
            url = r.get("href", "")
            if url and not self._is_aggregator_url(url):
                if self._validate_url(url):
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

    def _save_companies_to_db(self, db: Session, companies: List[Company]) -> int:
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
                )
                db.add(db_company)
                saved_count += 1

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

    def search_companies(
        self,
        db: Session,
        user_id: Optional[str] = None,
        cities: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        company_size: Optional[CompanySize] = None,
    ) -> CompanySearchResult:
        """
        Search for companies with self-building discovery.

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

        existing_names = [c.name for c in db.query(CompanyModel.name).all()]

        discovered = self.discover_companies(
            cities=cities,
            industries=industries,
            keywords=keywords,
            company_size=company_size,
            exclude_companies=existing_names,
        )

        newly_added = self._save_companies_to_db(db, discovered)

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

    def resolve_company_url_in_db(self, db: Session, company_id: str) -> Optional[str]:
        """
        Resolve and update career URL for a company in the database.
        Returns the resolved URL or None if resolution failed.
        """
        company = db.query(CompanyModel).filter(CompanyModel.id == company_id).first()
        if not company:
            return None

        resolved_url = self.resolve_career_url(company.name)
        if resolved_url:
            company.url = resolved_url
            company.url_verified = True
            db.commit()
            return resolved_url

        return None
