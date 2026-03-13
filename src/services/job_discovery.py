import json
import re
import urllib.request
import urllib.parse
from typing import List, Optional
from pydantic import BaseModel
from duckduckgo_search import DDGS
from litellm import completion
from src.config import settings

class Company(BaseModel):
    company_name: str
    career_url: str

class DiscoveryResult(BaseModel):
    companies: List[Company]

class JobDiscoveryService:
    def _search_tavily(self, query: str) -> Optional[List[dict]]:
        if not settings.TAVILY_API_KEY: return None
        try:
            print("Attempting Tavily Search...")
            url = "https://api.tavily.com/search"
            data = json.dumps({
                "query": query,
                "api_key": settings.TAVILY_API_KEY,
                "search_depth": "basic",
                "max_results": 10
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as response:
                res = json.loads(response.read())
                results = res.get("results", [])
                return [{"title": r.get("title"), "href": r.get("url"), "body": r.get("content")} for r in results]
        except Exception as e:
            print(f"Tavily failed: {e}")
            return None

    def _search_serper(self, query: str) -> Optional[List[dict]]:
        if not settings.SERPER_API_KEY: return None
        try:
            print("Attempting Serper (Google) Search...")
            url = "https://google.serper.dev/search"
            data = json.dumps({"q": query, "num": 10}).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={
                'X-API-KEY': settings.SERPER_API_KEY, 
                'Content-Type': 'application/json'
            })
            with urllib.request.urlopen(req, timeout=8) as response:
                res = json.loads(response.read())
                results = res.get("organic", [])
                return [{"title": r.get("title"), "href": r.get("link"), "body": r.get("snippet")} for r in results]
        except Exception as e:
            print(f"Serper failed: {e}")
            return None

    def _search_brave(self, query: str) -> Optional[List[dict]]:
        if not settings.BRAVE_API_KEY: return None
        try:
            print("Attempting Brave Search...")
            url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={
                'Accept': 'application/json', 
                'X-Subscription-Token': settings.BRAVE_API_KEY
            })
            with urllib.request.urlopen(req, timeout=8) as response:
                res = json.loads(response.read())
                results = res.get("web", {}).get("results", [])
                return [{"title": r.get("title"), "href": r.get("url"), "body": r.get("description")} for r in results]
        except Exception as e:
            print(f"Brave failed: {e}")
            return None

    def _search_ddg(self, query: str) -> List[dict]:
        try:
            print("Attempting DuckDuckGo Search (Fallback)...")
            return DDGS().text(query, max_results=10)
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []

    def discover_companies(self, query: str) -> List[Company]:
        # Implementation of the Rotational Fallback Pattern
        search_results = (
            self._search_tavily(query) or
            self._search_serper(query) or
            self._search_brave(query) or
            self._search_ddg(query)
        )
        
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
