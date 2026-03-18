from unittest.mock import patch
from src.services.job_discovery import Company


@patch("src.api.routers.jobs.discovery_service.discover_companies")
def test_discover_jobs(mock_discover, client):
    mock_discover.return_value = [
        Company(
            company_name="Mocked Inc",
            career_url="https://mocked.com/careers",
            url_verified=True,
        )
    ]
    response = client.post(
        "/api/v1/jobs/discover",
        json={
            "cities": ["Berlin"],
            "industries": ["AI"],
            "keywords": ["Python"],
            "company_size": "startup",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job discovery successful"
    assert data["total_found"] == 1
    assert len(data["companies"]) == 1
    assert data["companies"][0]["company_name"] == "Mocked Inc"
    assert data["companies"][0]["career_url"] == "https://mocked.com/careers"
    mock_discover.assert_called_once()


@patch("src.api.routers.jobs.discovery_service.discover_companies")
def test_discover_jobs_multiple_params(mock_discover, client):
    mock_discover.return_value = [
        Company(
            company_name="Berlin AI Corp", career_url="https://berlinai.com/careers"
        ),
        Company(
            company_name="Munich FinTech", career_url="https://munichfintech.com/jobs"
        ),
    ]
    response = client.post(
        "/api/v1/jobs/discover",
        json={
            "cities": ["Berlin", "Munich"],
            "industries": ["AI", "FinTech"],
            "keywords": ["Python"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] == 2
    assert len(data["companies"]) == 2
