import json
import re
import urllib.request
import urllib.parse
from typing import List, Optional
from pydantic import BaseModel
from duckduckgo_search import DDGS
from litellm import completion
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.config import settings
from src.models import Company as CompanyModel, CompanySize


class Company(BaseModel):
    company_name: str
    career_url: str


class DiscoveryResult(BaseModel):
    companies: List[Company]


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
            print("Attempting Tavily Search...")

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
            with urllib.request.urlopen(req, timeout=8) as response:
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
            print("Attempting Serper (Google) Search...")

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
            with urllib.request.urlopen(req, timeout=8) as response:
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
            print("Attempting Brave Search...")

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
            with urllib.request.urlopen(req, timeout=8) as response:
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
            print("Attempting DuckDuckGo Search (Fallback)...")

            search_query = query
            if exclude_companies:
                exclusion_text = f" -{' -'.join(exclude_companies[:10])}"
                search_query = query + exclusion_text

            return DDGS().text(search_query, max_results=20)
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    def _extract_companies_from_search(
        self, search_results: List[dict]
    ) -> List[Company]:
        if not search_results:
            return []

        search_context = json.dumps(search_results, indent=2)

        prompt = f"""
        You are an expert HR researcher. Based STRICTLY on the following search results, extract the software companies mentioned and their official career/jobs page URLs. 
        
        If no specific companies are mentioned in the search results, return an empty array [].
        DO NOT invent, guess, or hallucinate companies like Google or Microsoft unless they explicitly appear in the text below.
        
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
            discovery = DiscoveryResult.model_validate(parsed_data)
            return discovery.companies
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {raw_json}") from e

    def discover_companies(
        self, query: str, exclude_companies: Optional[List[str]] = None
    ) -> List[Company]:
        search_results = (
            self._search_tavily(query, exclude_companies)
            or self._search_serper(query, exclude_companies)
            or self._search_brave(query, exclude_companies)
            or self._search_ddg(query, exclude_companies)
        )

        return self._extract_companies_from_search(search_results)

    def _search_local_db(
        self,
        db: Session,
        city: Optional[str] = None,
        industry: Optional[str] = None,
        keywords: Optional[str] = None,
        company_size: Optional[CompanySize] = None,
    ) -> List[CompanyModel]:
        query = db.query(CompanyModel)

        if city:
            query = query.filter(CompanyModel.city.ilike(f"%{city}%"))

        if industry:
            query = query.filter(CompanyModel.industry.ilike(f"%{industry}%"))

        if keywords:
            query = query.filter(
                or_(
                    CompanyModel.name.ilike(f"%{keywords}%"),
                    CompanyModel.industry.ilike(f"%{keywords}%"),
                )
            )

        if company_size:
            query = query.filter(CompanyModel.company_size == company_size)

        return query.all()

    def _calculate_threshold(
        self,
        city: Optional[str],
        industry: Optional[str],
        keywords: Optional[str],
        company_size: Optional[CompanySize],
    ) -> int:
        has_filters = any([city, industry, keywords, company_size])
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
                )
                db.add(db_company)
                saved_count += 1

        if saved_count > 0:
            db.commit()

        return saved_count

    def search_companies(
        self,
        db: Session,
        city: Optional[str] = None,
        industry: Optional[str] = None,
        keywords: Optional[str] = None,
        company_size: Optional[CompanySize] = None,
    ) -> CompanySearchResult:
        local_companies = self._search_local_db(
            db, city, industry, keywords, company_size
        )
        threshold = self._calculate_threshold(city, industry, keywords, company_size)

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
                    }
                    for c in local_companies
                ],
                total_found=len(local_companies),
                newly_added=0,
                source="local",
            )

        existing_names = [c.name for c in db.query(CompanyModel.name).all()]

        search_parts = []
        if city:
            search_parts.append(f"companies in {city}")
        if industry:
            search_parts.append(f"{industry} companies")
        if company_size:
            size_map = {
                CompanySize.startup: "startup",
                CompanySize.hidden_champion: "hidden champion mid-sized",
                CompanySize.enterprise: "large enterprise",
            }
            search_parts.append(size_map.get(company_size, ""))
        if keywords:
            search_parts.append(keywords)

        search_query = (
            " ".join(search_parts) if search_parts else "software companies careers"
        )

        discovered = self.discover_companies(
            search_query, exclude_companies=existing_names
        )

        newly_added = self._save_companies_to_db(db, discovered)

        all_companies = self._search_local_db(
            db, city, industry, keywords, company_size
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
                }
                for c in all_companies
            ],
            total_found=len(all_companies),
            newly_added=newly_added,
            source="api_fallback" if newly_added > 0 else "local",
        )
