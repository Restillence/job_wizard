from unittest.mock import MagicMock, patch
from src.services.cover_letter import CoverLetterService
from src.models import Job, Company as CompanyModel


@patch("src.services.cover_letter.completion")
def test_generate_draft(mock_completion) -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='```json\n{"cover_letter": "Dear Hiring Manager, I am writing to apply...", "ai_match_rationale": "Strong match for Python"}\n```'
            )
        )
    ]
    mock_completion.return_value = mock_response

    service = CoverLetterService()

    company = CompanyModel(name="TechCorp", url="https://techcorp.example.com/careers")
    job = Job(
        title="Software Engineer",
        company=company,
        extracted_requirements={"req": "Python"},
        description="Desc",
    )
    resume_text = "Experienced in Python."

    cover_letter, rationale = service.generate_draft(job, resume_text)

    assert cover_letter == "Dear Hiring Manager, I am writing to apply..."
    assert rationale == "Strong match for Python"

    mock_completion.assert_called_once()
    args, kwargs = mock_completion.call_args
    assert "Software Engineer" in kwargs["messages"][0]["content"]
    assert "TechCorp" in kwargs["messages"][0]["content"]
    assert "Experienced in Python." in kwargs["messages"][0]["content"]
