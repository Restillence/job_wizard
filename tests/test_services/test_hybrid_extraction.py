import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.hybrid_extraction import (
    HybridExtractionService,
    ScrapedJobs,
    JobOpening,
)


def test_check_ats_footprint():
    service = HybridExtractionService()
    assert (
        service.check_ats_footprint("https://jobs.personio.de/engineering")
        == "personio"
    )
    assert service.check_ats_footprint("https://greenhouse.io/my-job") == "greenhouse"
    assert service.check_ats_footprint("https://workday.com/jobs") == "workday"
    assert (
        service.check_ats_footprint("https://company.com/index.php?ac=jobad")
        == "generic"
    )
    assert service.check_ats_footprint("https://custom-career-page.com/jobs") is None


@patch("src.services.hybrid_extraction.HybridExtractionService._extract_personio_jobs")
def test_scrape_jobs_ats_fast_path(mock_extract):
    mock_extract.return_value = ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="Software Engineer", application_url="https://test.com/job/1"
            )
        ]
    )

    service = HybridExtractionService()
    result = service.scrape_jobs("https://jobs.personio.de/engineering")

    assert len(result.jobs) == 1
    assert result.jobs[0].job_title == "Software Engineer"
    mock_extract.assert_called_once()


@patch(
    "src.services.hybrid_extraction.HybridExtractionService._extract_greenhouse_jobs"
)
def test_scrape_jobs_greenhouse(mock_extract):
    mock_extract.return_value = ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="DevOps Engineer",
                application_url="https://boards.greenhouse.io/test/job/1",
            )
        ]
    )

    service = HybridExtractionService()
    result = service.scrape_jobs("https://boards.greenhouse.io/company/jobs")

    assert len(result.jobs) == 1
    assert result.jobs[0].job_title == "DevOps Engineer"
    mock_extract.assert_called_once()


@patch("src.services.hybrid_extraction.asyncio.run")
def test_scrape_jobs_fallback(mock_run):
    mock_run.return_value = ScrapedJobs(
        jobs=[
            JobOpening(
                job_title="Custom Job", application_url="https://custom.com/job/1"
            )
        ]
    )

    service = HybridExtractionService()
    result = service.scrape_jobs("https://custom-career-page.com/jobs")

    assert len(result.jobs) == 1
    assert result.jobs[0].job_title == "Custom Job"
