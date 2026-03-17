import pytest
from unittest.mock import MagicMock, patch
from src.services.job_discovery import JobDiscoveryService, Company


@patch("src.services.job_discovery.settings")
@patch("src.services.job_discovery.completion")
@patch("src.services.job_discovery.DDGS")
def test_discover_companies(mock_ddgs_class, mock_completion, mock_settings) -> None:
    mock_settings.TAVILY_API_KEY = None
    mock_settings.SERPER_API_KEY = None
    mock_settings.BRAVE_API_KEY = None

    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Test Title", "href": "https://test.com"}
    ]
    mock_ddgs_class.return_value = mock_ddgs_instance

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='```json\n{"companies": [{"company_name": "TestCorp", "career_url": "https://testcorp.com/careers"}]}\n```'
            )
        )
    ]
    mock_completion.return_value = mock_response

    service = JobDiscoveryService()
    result = service.discover_companies("Test query")

    assert len(result) == 1
    assert result[0].company_name == "TestCorp"
    assert result[0].career_url == "https://testcorp.com/careers"

    mock_ddgs_instance.text.assert_called_once_with("Test query", max_results=20)
    mock_completion.assert_called_once()
