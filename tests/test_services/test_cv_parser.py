from unittest.mock import patch
from src.services.cv_parser import CVParserService, ParsedCV


@patch("src.services.cv_parser.call_llm")
def test_parse_cv_success(mock_call_llm):
    mock_call_llm.return_value = """{
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

    service = CVParserService()
    result = service.parse("John Smith\nSenior Dev\nPython, Docker")

    assert isinstance(result, ParsedCV)
    assert result.full_name == "John Smith"
    assert result.skills == ["Python", "Docker"]
    assert len(result.experience) == 1
    assert result.experience[0].title == "Senior Dev @ Corp | 2020-Present"


@patch("src.services.cv_parser.call_llm")
def test_parse_cv_with_markdown_wrapping(mock_call_llm):
    mock_call_llm.return_value = """```json
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

    service = CVParserService()
    result = service.parse("Jane\nPython developer")

    assert result.full_name == "Jane"
    assert result.skills == ["Python"]


@patch("src.services.cv_parser.call_llm")
def test_parse_cv_invalid_response(mock_call_llm):
    mock_call_llm.return_value = "not valid json at all"

    service = CVParserService()
    try:
        service.parse("some text")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
