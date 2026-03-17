import uuid
from unittest.mock import patch, MagicMock
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Company, CompanySize
from src.services.job_discovery import CompanySearchResult


def test_search_companies_local_only(client):
    db = TestingSessionLocal()

    for i in range(6):
        create_test_company(
            db, f"Berlin Tech {i}", f"https://berlin-tech-{i}.example.com/careers"
        )

    db.commit()

    with patch(
        "src.api.routers.companies.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[
                {
                    "id": "1",
                    "name": "Berlin Tech 1",
                    "city": "Berlin",
                    "industry": "Tech",
                    "company_size": "startup",
                    "url": "https://berlin-tech-1.example.com/careers",
                },
            ],
            total_found=1,
            newly_added=0,
            source="local",
        )

        response = client.get("/api/v1/companies/search", params={"keywords": "Berlin"})

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "local"

    db.close()


def test_search_companies_by_city(client):
    db = TestingSessionLocal()

    company = Company(
        id=str(uuid.uuid4()),
        name="Frankfurt Finance",
        city="Frankfurt",
        industry="Finance",
        company_size=CompanySize.enterprise,
        url="https://frankfurt-finance.example.com/careers",
    )
    db.add(company)
    db.commit()

    with patch(
        "src.api.routers.companies.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[
                {
                    "id": company.id,
                    "name": "Frankfurt Finance",
                    "city": "Frankfurt",
                    "industry": "Finance",
                    "company_size": "enterprise",
                    "url": "https://frankfurt-finance.example.com/careers",
                },
            ],
            total_found=1,
            newly_added=0,
            source="local",
        )

        response = client.get("/api/v1/companies/search", params={"city": "Frankfurt"})

    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] >= 1

    db.close()


def test_search_companies_by_size(client):
    db = TestingSessionLocal()

    company = Company(
        id=str(uuid.uuid4()),
        name="Tiny Startup",
        city="Berlin",
        industry="Tech",
        company_size=CompanySize.startup,
        url="https://tiny-startup.example.com/careers",
    )
    db.add(company)
    db.commit()

    with patch(
        "src.api.routers.companies.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[
                {
                    "id": company.id,
                    "name": "Tiny Startup",
                    "city": "Berlin",
                    "industry": "Tech",
                    "company_size": "startup",
                    "url": "https://tiny-startup.example.com/careers",
                },
            ],
            total_found=1,
            newly_added=0,
            source="local",
        )

        response = client.get(
            "/api/v1/companies/search", params={"company_size": "startup"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] >= 1

    db.close()


def test_search_companies_empty_params(client):
    with patch(
        "src.api.routers.companies.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[],
            total_found=0,
            newly_added=0,
            source="local",
        )

        response = client.get("/api/v1/companies/search")

    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert "total_found" in data
    assert "source" in data


def test_search_companies_api_fallback(client):
    with patch(
        "src.api.routers.companies.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[
                {
                    "id": "new-1",
                    "name": "New Company",
                    "city": None,
                    "industry": None,
                    "company_size": None,
                    "url": "https://new.example.com/careers",
                },
            ],
            total_found=1,
            newly_added=1,
            source="api_fallback",
        )

        response = client.get(
            "/api/v1/companies/search", params={"keywords": "nonexistent"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "api_fallback"
    assert data["newly_added"] == 1
