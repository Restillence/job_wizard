import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.job_discovery import JobDiscoveryService
from tests.conftest import TestingSessionLocal

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.anyio
@patch("src.services.job_discovery.settings")
@patch("src.services.job_discovery.acompletion")
@patch("src.services.job_discovery.DDGS")
@patch("httpx.AsyncClient.post")
@patch("httpx.AsyncClient.head")
async def test_discover_companies(mock_head, mock_post, mock_ddgs_class, mock_acompletion, mock_settings) -> None:
    mock_settings.TAVILY_API_KEY = "test-key"
    mock_settings.SERPER_API_KEY = None
    mock_settings.BRAVE_API_KEY = None
    mock_settings.ZAI_API_KEY = "test-key"
    mock_settings.ZAI_API_BASE = "https://test.com"

    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"results": [
            {
                "title": "Senior Developer at TestCorp",
                "url": "https://linkedin.com/jobs/123",
                "content": "TestCorp is hiring",
            }
        ]}
    )
    
    mock_head.return_value = MagicMock(status_code=200)

    mock_response_names = MagicMock()
    mock_response_names.choices = [
        MagicMock(
            message=MagicMock(content='{"results": [{"name": "TestCorp", "context_index": 0}, {"name": "AnotherCorp", "context_index": 0}]}')
        )
    ]

    mock_response_urls = MagicMock()
    mock_response_urls.choices = [
        MagicMock(
            message=MagicMock(
                content='{"companies": [{"company_name": "TestCorp", "career_url": "https://testcorp.com/careers", "city": "Berlin", "industry": "Software"}, {"company_name": "AnotherCorp", "career_url": "https://anothercorp.com/jobs", "city": "Berlin", "industry": "Software"}]}'
            )
        )
    ]

    mock_acompletion.side_effect = [mock_response_names, mock_response_urls]

    service = JobDiscoveryService()
    result = await service.discover_companies(
        cities=["Berlin"],
        industries=["Software"],
        keywords=["Python"],
    )

    assert len(result) == 2
    assert result[0].company_name == "TestCorp"
    assert result[0].career_url == "https://testcorp.com/careers"

    mock_post.assert_called()
    assert mock_acompletion.call_count == 2


@pytest.mark.anyio
@patch("src.services.job_discovery.settings")
@patch("src.services.job_discovery.acompletion")
@patch("src.services.job_discovery.DDGS")
@patch("httpx.AsyncClient.post")
@patch("httpx.AsyncClient.head")
async def test_discover_companies_with_exclusions(
    mock_head, mock_post, mock_ddgs_class, mock_acompletion, mock_settings
) -> None:
    mock_settings.TAVILY_API_KEY = "test-key"
    mock_settings.SERPER_API_KEY = None
    mock_settings.BRAVE_API_KEY = None
    mock_settings.ZAI_API_KEY = "test-key"
    mock_settings.ZAI_API_BASE = "https://test.com"

    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"results": [
            {
                "title": "Developer at NewCorp",
                "url": "https://newcorp.com/careers",
                "content": "NewCorp hiring",
            }
        ]}
    )
    mock_head.return_value = MagicMock(status_code=200)

    mock_response_names = MagicMock()
    mock_response_names.choices = [
        MagicMock(message=MagicMock(content='{"results": [{"name": "NewCorp", "context_index": 0}]}'))
    ]

    mock_response_urls = MagicMock()
    mock_response_urls.choices = [
        MagicMock(
            message=MagicMock(
                content='{"companies": [{"company_name": "NewCorp", "career_url": "https://newcorp.com/careers", "city": "Munich", "industry": null}]}'
            )
        )
    ]

    mock_acompletion.side_effect = [mock_response_names, mock_response_urls]

    service = JobDiscoveryService()
    result = await service.discover_companies(
        cities=["Munich"],
        exclude_companies=["TestCorp", "AnotherCorp"],
    )

@pytest.mark.anyio
@patch("src.services.job_discovery.JobDiscoveryService.discover_companies")
async def test_search_companies_local_hit(mock_discover, db_session) -> None:
    from src.models import Company as CompanyModel, CompanySize
    from src.services.job_discovery import JobDiscoveryService
    
    # Add a company to DB
    company = CompanyModel(
        name="LocalCorp",
        url="https://localcorp.com/careers",
        city="Berlin",
        industry="Software",
        company_size=CompanySize.startup,
        url_verified=True
    )
    db_session.add(company)
    db_session.commit()
    
    service = JobDiscoveryService()
    
    # Search for Berlin (threshold for specific query is 5)
    # If we have 1 company, it's < 5, so it should trigger discovery
    mock_discover.return_value = []
    
    result = await service.search_companies(
        db=db_session,
        cities=["Berlin"],
        industries=["Software"]
    )
    
    assert result.total_found >= 1
    mock_discover.assert_called_once()


@pytest.mark.anyio
@patch("src.services.job_discovery.JobDiscoveryService.discover_companies")
async def test_search_companies_threshold_met(mock_discover, db_session) -> None:
    from src.models import Company as CompanyModel, CompanySize
    from src.services.job_discovery import JobDiscoveryService
    
    # Add 6 companies to DB (specific threshold is 5)
    for i in range(6):
        company = CompanyModel(
            name=f"LocalCorp {i}",
            url=f"https://localcorp{i}.com/careers",
            city="Berlin",
            industry="Software",
            company_size=CompanySize.startup,
            url_verified=True
        )
        db_session.add(company)
    db_session.commit()
    
    service = JobDiscoveryService()
    
    result = await service.search_companies(
        db=db_session,
        cities=["Berlin"],
        industries=["Software"]
    )
    
    assert result.total_found >= 6
    assert result.source == "local"
    mock_discover.assert_not_called()


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
