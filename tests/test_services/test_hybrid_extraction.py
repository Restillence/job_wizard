import pytest
from unittest.mock import MagicMock, patch
from src.services.hybrid_extraction import HybridExtractionService

def test_check_ats_footprint():
    service = HybridExtractionService()
    assert service.check_ats_footprint("https://jobs.personio.de/engineering") is True
    assert service.check_ats_footprint("https://greenhouse.io/my-job") is True
    assert service.check_ats_footprint("https://workday.com/jobs") is True
    assert service.check_ats_footprint("https://company.com/index.php?ac=jobad") is True
    assert service.check_ats_footprint("https://custom-career-page.com/jobs") is False

@patch("src.services.hybrid_extraction.HybridExtractionService._crawl4ai_fallback")
def test_scrape_jobs_ats_fast_path(mock_fallback):
    service = HybridExtractionService()
    result = service.scrape_jobs("https://jobs.personio.de/engineering")
    
    assert len(result.jobs) == 1
    assert result.jobs[0].job_title == "Software Engineer (ATS)"
    mock_fallback.assert_not_called()

# We can skip testing _crawl4ai_fallback extensively here because it involves async playwright setup
# which might be tricky to mock completely. For now, checking the ATS fast-path logic is sufficient.
