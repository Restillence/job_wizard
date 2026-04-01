from unittest.mock import patch, MagicMock
from src.services.cv_parser import CVParserService, ParsedCV


def test_parse_cv_success():
    service = CVParserService()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """{
        "full_name": "John Smith",
        "email": "john@email.com",
        "phone": "+491234567",
        "summary": "Experienced Python developer",
        "experience": [{"title": "Senior Dev @ Corp | 2020-Present", "content": "Built systems"}],
        "education": [{"title": "B.Sc. CS | TU Berlin | 2020", "content": "CS degree"}],
        "skills": ["Python", "Docker"],
        "languages": ["English"],
        "certifications": [],
        "additional_sections": []
    }"""

    with patch("src.services.cv_parser.completion", return_value=mock_response):
        result = service.parse("John Smith\nSenior Dev\nPython, Docker")

    assert isinstance(result, ParsedCV)
    assert result.full_name == "John Smith"
    assert result.skills == ["Python", "Docker"]
    assert len(result.experience) == 1
    assert result.experience[0].title == "Senior Dev @ Corp | 2020-Present"


def test_parse_cv_with_markdown_wrapping():
    service = CVParserService()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """```json
{
    "full_name": "Jane",
    "email": "",
    "phone": "",
    "summary": null,
    "experience": [],
    "education": [],
    "skills": ["Python"],
    "languages": [],
    "certifications": [],
    "additional_sections": []
}
```"""

    with patch("src.services.cv_parser.completion", return_value=mock_response):
        result = service.parse("Jane\nPython developer")

    assert result.full_name == "Jane"
    assert result.skills == ["Python"]


def test_parse_cv_invalid_response():
    service = CVParserService()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not valid json at all"

    with patch("src.services.cv_parser.completion", return_value=mock_response):
        try:
            service.parse("some text")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
