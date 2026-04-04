import json
import re
from pydantic import BaseModel
from src.services.llm_utils import call_llm
from src.services.cv_parser import ParsedCV


class TailoredSection(BaseModel):
    title: str
    content: str


class TailoredCV(BaseModel):
    summary: str = ""
    experience: list[TailoredSection] = []
    education: list[TailoredSection] = []
    skills: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []
    additional_sections: list[TailoredSection] = []
    tailoring_notes: str = ""


class CoverLetterResult(BaseModel):
    cover_letter: str
    ai_match_rationale: str


class CVGeneratorService:
    def tailor_cv(
        self,
        parsed_cv: ParsedCV,
        job_title: str,
        job_description: str,
        job_requirements: dict,
    ) -> TailoredCV:
        cv_json = parsed_cv.model_dump_json(indent=2)

        prompt = f"""You are an expert CV tailor. Given a parsed CV and a target job, create a tailored version.

RULES - CRITICAL:
1. ONLY reorder, emphasize, or de-emphasize existing content. NEVER fabricate experience, skills, or education.
2. Reorder skills so job-relevant skills appear first.
3. Reorder experience bullet points so the most relevant ones come first.
4. Rewrite the professional summary to target this specific role (using only real information).
5. If a skill is mentioned in the job but NOT in the CV, do NOT add it.
6. Keep ALL original information - don't delete anything, just reorder.

TARGET JOB:
Title: {job_title}
Description: {job_description}
Requirements: {json.dumps(job_requirements)}

PARSED CV:
{cv_json}

Return ONLY a JSON object matching this schema:
{{
    "summary": "Tailored professional summary (2-3 sentences)",
    "experience": [{{"title": "Job Title @ Company | Dates", "content": "Reordered bullet points"}}],
    "education": [{{"title": "Degree | Institution | Year", "content": "details"}}],
    "skills": ["reordered", "skills", "most", "relevant", "first"],
    "languages": ["same as original"],
    "certifications": ["same as original"],
    "additional_sections": [{{"title": "name", "content": "content"}}],
    "tailoring_notes": "Brief explanation of what was changed and why"
}}"""

        raw = call_llm([{"role": "user", "content": prompt}])
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n|\n```$", "", raw)

        try:
            data = json.loads(raw)
            return TailoredCV(**data)
        except Exception as e:
            raise ValueError(f"Failed to tailor CV: {e}") from e

    def generate_cover_letter(
        self,
        parsed_cv: ParsedCV,
        job_title: str,
        company_name: str,
        job_description: str,
        job_requirements: dict,
    ) -> CoverLetterResult:
        cv_json = parsed_cv.model_dump_json(indent=2)

        prompt = f"""You are an expert cover letter writer. Write a professional, compelling cover letter for this job application.

RULES:
1. Use ONLY real information from the CV. Never fabricate anything.
2. Write in a professional but natural tone.
3. Keep it to 3-4 paragraphs.
4. Address specific job requirements with relevant experience.
5. Do NOT use placeholders like [Your Name] - use [REDACTED] for PII.

TARGET JOB:
Title: {job_title}
Company: {company_name}
Description: {job_description}
Requirements: {json.dumps(job_requirements)}

APPLICANT'S CV (PII stripped):
{cv_json}

Return ONLY a JSON object:
{{
    "cover_letter": "Full cover letter text",
    "ai_match_rationale": "Brief rationale (EU AI Act) explaining why this candidate matches this job, listing specific skill/experience matches"
}}"""

        raw = call_llm([{"role": "user", "content": prompt}])
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n|\n```$", "", raw)

        try:
            data = json.loads(raw)
            return CoverLetterResult(**data)
        except Exception as e:
            raise ValueError(f"Failed to generate cover letter: {e}") from e
