import json
import re
from src.config import settings
from src.models import Job
from src.services.llm_utils import call_llm


class CoverLetterService:
    def generate_draft(self, job: Job, resume_text: str) -> tuple[str, str]:
        """
        Generates a cover letter draft and the AI match rationale.
        Returns: (cover_letter_text, ai_match_rationale)
        """
        prompt = f"""
        You are an expert career assistant. Based on the user's resume and the target job description, draft a professional cover letter.
        Also provide a short rationale (EU AI Act logging) of why this user matches this job.
        
        Job Details:
        Title: {job.title}
        Company: {job.company.name if job.company else "Unknown"}
        Requirements: {job.extracted_requirements}
        Description: {job.description}
        
        User Resume (PII stripped):
        {resume_text}
        
        Return ONLY a JSON object exactly matching this schema:
        {{
            "cover_letter": "Dear Hiring Manager... (full text)",
            "ai_match_rationale": "User matches 3/5 requirements including Python and Docker..."
        }}
        Do not include markdown formatting like ```json.
        """

        raw_json = call_llm([{"role": "user", "content": prompt}])

        if raw_json.startswith("```"):
            raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)

        try:
            parsed = json.loads(raw_json)
            return parsed.get("cover_letter", ""), parsed.get("ai_match_rationale", "")
        except Exception as e:
            raise ValueError(
                f"Failed to parse LLM cover letter response: {raw_json}"
            ) from e
