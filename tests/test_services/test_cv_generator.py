import os
from unittest.mock import patch, MagicMock
from src.services.cv_parser import ParsedCV, CVSection
from src.services.cv_generator import (
    TailoredCV,
    TailoredSection,
    CoverLetterResult,
    CVGeneratorService,
)
from src.services.docx_renderer import render_cv, render_cover_letter


def _sample_parsed_cv():
    return ParsedCV(
        full_name="[REDACTED]",
        email="[REDACTED]",
        phone="[REDACTED]",
        summary="Experienced Python developer",
        experience=[
            CVSection(
                title="Senior Dev @ TechCorp | 2021-Present",
                content="Built Python systems\nLed team of 4",
            )
        ],
        education=[CVSection(title="B.Sc. CS | TU Berlin | 2019", content="CS degree")],
        skills=["Python", "Docker", "Kubernetes"],
        languages=["English (Fluent)", "German (Native)"],
    )


def _sample_tailored_cv():
    return TailoredCV(
        summary="Experienced Python developer targeting backend roles",
        experience=[
            TailoredSection(
                title="Senior Dev @ TechCorp | 2021-Present",
                content="Built Python systems\nLed team of 4",
            )
        ],
        education=[
            TailoredSection(title="B.Sc. CS | TU Berlin | 2019", content="CS degree")
        ],
        skills=["Python", "Docker", "Kubernetes"],
        languages=["English (Fluent)", "German (Native)"],
        tailoring_notes="Reordered skills to match job",
    )


def test_tailor_cv():
    service = CVGeneratorService()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """{
        "summary": "Tailored summary",
        "experience": [{"title": "Senior Dev @ TechCorp | 2021-Present", "content": "Built Python systems"}],
        "education": [{"title": "B.Sc. CS | TU Berlin | 2019", "content": "CS degree"}],
        "skills": ["Python", "Docker", "Kubernetes"],
        "languages": ["English (Fluent)", "German (Native)"],
        "certifications": [],
        "additional_sections": [],
        "tailoring_notes": "Reordered skills"
    }"""

    with patch("src.services.cv_generator.completion", return_value=mock_response):
        result = service.tailor_cv(
            parsed_cv=_sample_parsed_cv(),
            job_title="Python Developer",
            job_description="Looking for Python expert",
            job_requirements={"skills": ["Python"]},
        )

    assert isinstance(result, TailoredCV)
    assert result.tailoring_notes == "Reordered skills"
    assert "Python" in result.skills


def test_generate_cover_letter():
    service = CVGeneratorService()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """{
        "cover_letter": "Dear Hiring Manager,\\n\\nI am writing to apply...",
        "ai_match_rationale": "User has 3/5 required skills"
    }"""

    with patch("src.services.cv_generator.completion", return_value=mock_response):
        result = service.generate_cover_letter(
            parsed_cv=_sample_parsed_cv(),
            job_title="Python Developer",
            company_name="TestCorp",
            job_description="Python backend role",
            job_requirements={"skills": ["Python"]},
        )

    assert isinstance(result, CoverLetterResult)
    assert "Dear" in result.cover_letter
    assert result.ai_match_rationale


def test_render_cv_creates_docx():
    tailored = _sample_tailored_cv()
    parsed = _sample_parsed_cv()
    output_path = "uploads/test_output_cv.docx"

    try:
        result = render_cv(tailored, parsed, output_path)
        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_render_cover_letter_creates_docx():
    parsed = _sample_parsed_cv()
    cover_letter = CoverLetterResult(
        cover_letter="Dear Hiring Manager,\n\nI am applying for the role.\n\nBest regards",
        ai_match_rationale="Good match",
    )
    output_path = "uploads/test_output_cl.docx"

    try:
        result = render_cover_letter(cover_letter, parsed, "TestCorp", output_path)
        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_render_cv_with_empty_sections():
    tailored = TailoredCV(summary="A brief summary")
    parsed = ParsedCV(full_name="Test User", email="test@test.com")
    output_path = "uploads/test_empty_cv.docx"

    try:
        result = render_cv(tailored, parsed, output_path)
        assert os.path.exists(result)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
