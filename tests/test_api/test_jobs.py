from unittest.mock import patch, MagicMock, AsyncMock
from src.services.job_discovery import Company
from src.services.hybrid_extraction import ScrapedJobs, JobOpening


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


@patch("src.api.routers.jobs.extraction_service.scrape_jobs")
def test_add_job_by_url_success(mock_scrape, client):
    mock_scrape.return_value = ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="Senior Python Developer",
                application_url="https://example.com/jobs/python-dev",
                company_name="TechCorp",
                requirements=["Python", "FastAPI", "Docker"],
                description="We are looking for a senior Python developer...",
                location="Berlin",
            )
        ]
    )

    response = client.post(
        "/api/v1/jobs/add",
        json={"url": "https://example.com/jobs/python-dev"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["title"] == "Senior Python Developer"
    assert data["company_name"] == "TechCorp"
    assert data["location"] == "Berlin"
    assert data["source"] == "manual_url"
    assert data["is_new"] is True


@patch("src.api.routers.jobs.extraction_service.scrape_jobs")
def test_add_job_existing(mock_scrape, client):
    from tests.conftest import TestingSessionLocal, create_test_company
    from src.models import Job
    import uuid

    db = TestingSessionLocal()
    company = create_test_company(db, "TechCorp")
    existing_job = Job(
        id=str(uuid.uuid4()),
        source_url="https://example.com/jobs/existing",
        title="Existing Job",
        company_id=company.id,
        description="Existing description",
        source="manual_url",
        dedup_hash="somehash",
    )
    db.add(existing_job)
    db.commit()
    existing_id = existing_job.id
    db.close()

    mock_scrape.return_value = ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="Existing Job Updated",
                application_url="https://example.com/jobs/existing",
                requirements=[],
                description="Updated description",
                location="Berlin",
            )
        ]
    )

    response = client.post(
        "/api/v1/jobs/add",
        json={"url": "https://example.com/jobs/existing"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_new"] is False
    assert data["job_id"] == existing_id


@patch("src.api.routers.jobs.extraction_service.scrape_single_job")
@patch("src.api.routers.jobs.extraction_service.scrape_jobs")
def test_add_job_url_scraping_fails_no_text(mock_scrape, mock_single, client):
    mock_scrape.return_value = ScrapedJobs(jobs=[])
    mock_single.return_value = None

    response = client.post(
        "/api/v1/jobs/add",
        json={"url": "https://example.com/no-jobs-here"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Could not extract" in detail or "raw_text" in detail


def test_add_job_no_url_no_text(client):
    response = client.post(
        "/api/v1/jobs/add",
        json={},
    )

    assert response.status_code == 400
    assert "at least one" in response.json()["detail"].lower()


def test_add_job_aggregator_url_no_text(client):
    response = client.post(
        "/api/v1/jobs/add",
        json={"url": "https://de.indeed.com/viewjob?jk=abc123"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "indeed.com" in detail
    assert "raw_text" in detail


@patch("src.api.routers.jobs.extraction_service.extract_from_raw_text")
def test_add_job_aggregator_url_with_text(mock_extract, client):
    mock_extract.return_value = JobOpening(
        job_title="Data Scientist",
        application_url="https://de.indeed.com/viewjob?jk=abc123",
        company_name="InsureTech GmbH",
        requirements=["Python", "Machine Learning"],
        description="We are looking for a data scientist...",
        location="Frankfurt",
    )

    response = client.post(
        "/api/v1/jobs/add",
        json={
            "url": "https://de.indeed.com/viewjob?jk=abc123",
            "raw_text": "Data Scientist at InsureTech GmbH. Requirements: Python, ML...",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Data Scientist"
    assert data["company_name"] == "InsureTech GmbH"
    assert data["is_new"] is True
    assert data["source"] == "manual_url"


@patch("src.api.routers.jobs.extraction_service.extract_from_raw_text")
def test_add_job_text_only(mock_extract, client):
    mock_extract.return_value = JobOpening(
        job_title="Frontend Developer",
        application_url="manual://frontend-developer",
        company_name="WebAgency",
        requirements=["React", "TypeScript"],
        description="Build amazing UIs...",
        location="Munich",
    )

    response = client.post(
        "/api/v1/jobs/add",
        json={
            "raw_text": "Frontend Developer at WebAgency. React, TypeScript required. Munich.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Frontend Developer"
    assert data["company_name"] == "WebAgency"
    assert data["source"] == "manual_text"
    assert data["is_new"] is True


@patch("src.api.routers.jobs.extraction_service.extract_from_raw_text")
@patch("src.api.routers.jobs.extraction_service.scrape_single_job")
@patch("src.api.routers.jobs.extraction_service.scrape_jobs")
def test_add_job_url_fails_falls_back_to_text(
    mock_scrape, mock_single, mock_extract, client
):
    mock_scrape.return_value = ScrapedJobs(jobs=[])
    mock_single.return_value = None
    mock_extract.return_value = JobOpening(
        job_title="Backend Developer",
        application_url="https://example.com/jobs/123",
        company_name="Example Corp",
        requirements=["Java", "Spring"],
        description="Backend development role...",
        location="Hamburg",
    )

    response = client.post(
        "/api/v1/jobs/add",
        json={
            "url": "https://example.com/jobs/123",
            "raw_text": "Backend Developer at Example Corp. Java, Spring required.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Backend Developer"
    assert data["company_name"] == "Example Corp"
    mock_scrape.assert_called_once()
    mock_extract.assert_called_once()


@patch("src.api.routers.jobs.extraction_service.extract_from_raw_text")
def test_add_job_text_extraction_fails(mock_extract, client):
    mock_extract.return_value = None

    response = client.post(
        "/api/v1/jobs/add",
        json={"raw_text": "random gibberish text that is not a job posting"},
    )

    assert response.status_code == 502
