import json
import re
from typing import List
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
    def discover_companies(self, query: str) -> List[Company]:
        # 1. Use DuckDuckGo Search (Free, no API key needed)
        search_results = DDGS().text(query, max_results=5)
        search_context = json.dumps(search_results, indent=2)

        # 2. Feed context to LLM for extraction
        prompt = f"""
        You are an expert HR researcher. Based on the following search results, extract the top 2 software companies and their official career/jobs page URLs.
        
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

        # Clean up markdown code blocks if the LLM ignores instructions
        if raw_json.startswith("```"):
            raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

        try:
            parsed_data = json.loads(raw_json)
            discovery = DiscoveryResult.model_validate(parsed_data)
            return discovery.companies
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {raw_json}") from e
