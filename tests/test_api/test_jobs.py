from unittest.mock import patch
from src.services.job_discovery import Company


@patch("src.api.routers.jobs.discovery_service.discover_companies")
def test_discover_jobs(mock_discover, client):
    mock_discover.return_value = [
        Company(company_name="Mocked Inc", career_url="https://mocked.com/careers")
    ]
    response = client.post(
        "/api/v1/jobs/discover", json={"query": "Find AI engineering roles in Berlin"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job discovery successful"
    assert data["query"] == "Find AI engineering roles in Berlin"
    assert len(data["companies"]) == 1
    assert data["companies"][0]["company_name"] == "Mocked Inc"
    assert data["companies"][0]["career_url"] == "https://mocked.com/careers"
    mock_discover.assert_called_once_with("Find AI engineering roles in Berlin")
