from unittest.mock import MagicMock, patch
from src.services.job_discovery import JobDiscoveryService


@patch("src.services.job_discovery.settings")
@patch("src.services.job_discovery.completion")
@patch("src.services.job_discovery.DDGS")
def test_discover_companies(mock_ddgs_class, mock_completion, mock_settings) -> None:
    mock_settings.TAVILY_API_KEY = None
    mock_settings.SERPER_API_KEY = None
    mock_settings.BRAVE_API_KEY = None
    mock_settings.ZAI_API_KEY = "test-key"
    mock_settings.ZAI_API_BASE = "https://test.com"

    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {
            "title": "Senior Developer at TestCorp",
            "href": "https://linkedin.com/jobs/123",
            "body": "TestCorp is hiring",
        }
    ]
    mock_ddgs_class.return_value = mock_ddgs_instance

    mock_response_names = MagicMock()
    mock_response_names.choices = [
        MagicMock(
            message=MagicMock(content='{"companies": ["TestCorp", "AnotherCorp"]}')
        )
    ]

    mock_response_urls = MagicMock()
    mock_response_urls.choices = [
        MagicMock(
            message=MagicMock(
                content='{"companies": [{"company_name": "TestCorp", "career_url": "https://testcorp.com/careers"}, {"company_name": "AnotherCorp", "career_url": "https://anothercorp.com/jobs"}]}'
            )
        )
    ]

    mock_completion.side_effect = [mock_response_names, mock_response_urls]

    service = JobDiscoveryService()
    result = service.discover_companies(
        cities=["Berlin"],
        industries=["Software"],
        keywords=["Python"],
    )

    assert len(result) == 2
    assert result[0].company_name == "TestCorp"
    assert result[0].career_url == "https://testcorp.com/careers"

    mock_ddgs_instance.text.assert_called()
    assert mock_completion.call_count == 2


@patch("src.services.job_discovery.settings")
@patch("src.services.job_discovery.completion")
@patch("src.services.job_discovery.DDGS")
def test_discover_companies_with_exclusions(
    mock_ddgs_class, mock_completion, mock_settings
) -> None:
    mock_settings.TAVILY_API_KEY = None
    mock_settings.SERPER_API_KEY = None
    mock_settings.BRAVE_API_KEY = None
    mock_settings.ZAI_API_KEY = "test-key"
    mock_settings.ZAI_API_BASE = "https://test.com"

    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {
            "title": "Developer at NewCorp",
            "href": "https://newcorp.com/careers",
            "body": "NewCorp hiring",
        }
    ]
    mock_ddgs_class.return_value = mock_ddgs_instance

    mock_response_names = MagicMock()
    mock_response_names.choices = [
        MagicMock(message=MagicMock(content='{"companies": ["NewCorp"]}'))
    ]

    mock_response_urls = MagicMock()
    mock_response_urls.choices = [
        MagicMock(
            message=MagicMock(
                content='{"companies": [{"company_name": "NewCorp", "career_url": "https://newcorp.com/careers"}]}'
            )
        )
    ]

    mock_completion.side_effect = [mock_response_names, mock_response_urls]

    service = JobDiscoveryService()
    result = service.discover_companies(
        cities=["Munich"],
        exclude_companies=["TestCorp", "AnotherCorp"],
    )

    assert len(result) == 1
    assert result[0].company_name == "NewCorp"


def test_build_search_query():
    from src.models import CompanySize

    service = JobDiscoveryService()

    query = service._build_search_query(
        cities=["Berlin", "Munich"],
        industries=["AI", "FinTech"],
        keywords=["Python"],
        company_size=CompanySize.startup,
    )

    assert "Berlin" in query
    assert "Munich" in query
    assert "AI" in query
    assert "FinTech" in query
    assert "Python" in query
    assert "startup" in query
    assert "companies careers hiring" in query
    assert "-linkedin" in query
    assert "-indeed" in query
    assert "-glassdoor" in query


def test_is_aggregator_url():
    service = JobDiscoveryService()

    assert service._is_aggregator_url("https://linkedin.com/jobs/123") is True
    assert service._is_aggregator_url("https://indeed.com/viewjob?jk=xyz") is True
    assert service._is_aggregator_url("https://glassdoor.com/Job/jobs.htm") is True
    assert service._is_aggregator_url("https://careers.sap.com") is False
    assert service._is_aggregator_url("https://jobs.zalando.com") is False


def test_dedupe_companies():
    from src.services.job_discovery import Company

    service = JobDiscoveryService()

    companies = [
        Company(company_name="TestCorp", career_url="https://testcorp.com/careers"),
        Company(company_name="TestCorp", career_url="https://testcorp.com/careers/"),
        Company(company_name="OtherCorp", career_url="https://othercorp.com/jobs"),
    ]

    result = service._dedupe_companies(companies)

    assert len(result) == 2
