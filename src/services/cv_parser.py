import json
import re
from typing import Optional
from pydantic import BaseModel
from src.services.llm_utils import call_llm


class CVSection(BaseModel):
    title: str
    content: str


class ParsedCV(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    summary: Optional[str] = None
    experience: list[CVSection] = []
    education: list[CVSection] = []
    skills: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []
    additional_sections: list[CVSection] = []


class CVParserService:
    def parse(self, resume_text: str) -> ParsedCV:
        prompt = f"""You are a CV/Resume parser. Extract the structured content from this resume text.
Return ONLY a JSON object matching this exact schema:
{{
    "full_name": "string or empty",
    "email": "string or empty",
    "phone": "string or empty",
    "summary": "string or null",
    "experience": [{{"title": "Job Title @ Company | Dates", "content": "bullet points as single string"}}],
    "education": [{{"title": "Degree | Institution | Year", "content": "details as string"}}],
    "skills": ["skill1", "skill2"],
    "languages": ["English (Fluent)", "German (Native)"],
    "certifications": ["cert name"],
    "additional_sections": [{{"title": "section name", "content": "content string"}}]
}}

Rules:
- Preserve ALL information from the original resume
- Keep bullet points in content fields as text with newlines
- Extract skills as individual items
- If a section is empty, use an empty list

Resume text:
{resume_text}"""

        response = call_llm([{"role": "user", "content": prompt}])

        raw = response
        if raw.startswith("```"):
            import re

            raw = re.sub(r"^```(?:json)?\n|\n```$", "", raw)

        try:
            data = json.loads(raw)
            return ParsedCV(**data)
        except Exception as e:
            raise ValueError(f"Failed to parse CV: {e}") from e
