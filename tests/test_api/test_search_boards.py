import uuid
from unittest.mock import patch, MagicMock
from tests.conftest import TestingSessionLocal, create_test_company
from src.models import Job
from src.services.job_sources.base import NormalizedJob


def _make_normalized_job(**overrides):
    defaults = {
        "title": "Python Developer",
        "company_name": "Board Corp",
        "source_url": "https://example.com/jobs/1",
        "source": "arbeitnow",
        "source_id": "test-slug",
        "description": "Build Python things",
        "location_city": "Berlin",
        "location_country": "DE",
        "remote": False,
    }
    defaults.update(overrides)
    return NormalizedJob(**defaults)


class TestSearchBoardsEndpoint:
    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_returns_jobs(self, mock_search, client):
        db = TestingSessionLocal()
        db.query(Job).delete()
        db.commit()

        mock_search.return_value = [
            _make_normalized_job(
                title="Python Dev",
                company_name="Search Boards Corp",
                source_url="https://example.com/sb/1",
            )
        ]

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"query": "Python", "city": "Berlin", "country": "DE"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_found"] >= 1
        assert data["newly_added"] >= 1
        assert any(j["title"] == "Python Dev" for j in data["jobs"])
        db.close()

    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_empty_results(self, mock_search, client):
        mock_search.return_value = []

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"query": "NonexistentJob12345"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_found"] == 0
        assert data["newly_added"] == 0
        assert data["jobs"] == []

    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_deduplicates(self, mock_search, client):
        db = TestingSessionLocal()
        db.query(Job).delete()
        db.commit()

        mock_search.return_value = [
            _make_normalized_job(
                title="Python Dev",
                company_name="Dedup Corp",
                source_url="https://example.com/dedup/1",
            ),
            _make_normalized_job(
                title="Python Dev",
                company_name="Dedup Corp",
                source_url="https://example.com/dedup/2",
                source="arbeitsagentur",
                location_city="Berlin",
            ),
        ]

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"query": "Python", "city": "Berlin"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["newly_added"] == 1
        assert data["updated"] == 1
        db.close()

    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_with_keywords(self, mock_search, client):
        db = TestingSessionLocal()
        db.query(Job).delete()
        db.commit()

        mock_search.return_value = []

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"keywords": ["Python", "FastAPI"], "city": "Munich"},
        )

        assert response.status_code == 200

        mock_search.assert_called_once()
        call_args = mock_search.call_args[0][0]
        assert call_args.keywords == ["Python", "FastAPI"]
        assert call_args.city == "Munich"
        db.close()

    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_default_country(self, mock_search, client):
        mock_search.return_value = []

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"query": "Python"},
        )

        assert response.status_code == 200
        mock_search.assert_called_once()
        call_args = mock_search.call_args[0][0]
        assert call_args.country == "DE"

    @patch("src.api.routers.jobs.search_all")
    def test_search_boards_creates_company(self, mock_search, client):
        db = TestingSessionLocal()
        db.query(Job).delete()
        db.commit()

        mock_search.return_value = [
            _make_normalized_job(
                title="Dev",
                company_name="New Board Company XYZ",
                source_url="https://example.com/nbc/1",
            )
        ]

        response = client.post(
            "/api/v1/jobs/search-boards",
            json={"query": "Dev"},
        )

        assert response.status_code == 200
        from src.models import Company

        company = (
            db.query(Company).filter(Company.name == "New Board Company XYZ").first()
        )
        assert company is not None
        assert company.url_verified is False
        db.close()
