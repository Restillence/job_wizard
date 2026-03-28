from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from src.services.job_sources.arbeitnow import ArbeitnowSource
from src.services.job_sources.base import SearchParams


def _make_api_item(**overrides):
    item = {
        "slug": "python-dev-testcorp-berlin",
        "url": "https://www.arbeitnow.com/jobs/python-dev-testcorp-berlin",
        "title": "Python Developer",
        "company_name": "TestCorp",
        "location": "Berlin, Germany",
        "country_code": "DE",
        "description": "Build amazing things with Python",
        "created_at": "2025-01-15T10:00:00Z",
        "remote": False,
        "salary": "50000 - 70000 EUR",
        "tags": ["python", "django"],
        "visa_sponsorship": True,
        "job_type": "full-time",
    }
    item.update(overrides)
    return item


class TestArbeitnowSource:
    def test_name(self):
        source = ArbeitnowSource()
        assert source.name == "arbeitnow"

    def test_supported_countries(self):
        source = ArbeitnowSource()
        assert set(source.supported_countries) == {"DE", "AT", "CH"}


class TestParseSingle:
    def test_basic_parsing(self):
        source = ArbeitnowSource()
        params = SearchParams(country="DE")
        item = _make_api_item()
        job = source._parse_single(item, params)

        assert job is not None
        assert job.title == "Python Developer"
        assert job.company_name == "TestCorp"
        assert job.source == "arbeitnow"
        assert job.source_id == "python-dev-testcorp-berlin"
        assert job.location_city == "Berlin, Germany"
        assert job.location_country == "DE"
        assert job.remote is False
        assert job.salary_min == 50000.0
        assert job.salary_max == 70000.0
        assert job.tags == ["python", "django"]
        assert job.visa_sponsorship is True

    def test_no_url_no_slug_returns_none(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(url="", slug="")
        assert source._parse_single(item, params) is None

    def test_slug_used_as_url_fallback(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(url="")
        job = source._parse_single(item, params)
        assert (
            job.source_url
            == "https://www.arbeitnow.com/jobs/python-dev-testcorp-berlin"
        )

    def test_no_title_returns_none(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(title="")
        assert source._parse_single(item, params) is None

    def test_no_company_returns_none(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(company_name="")
        assert source._parse_single(item, params) is None

    def test_created_at_integer_timestamp(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(created_at=1705312800)
        job = source._parse_single(item, params)
        assert job.posted_at is not None
        assert isinstance(job.posted_at, datetime)

    def test_created_at_string_iso(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(created_at="2025-03-01T12:00:00Z")
        job = source._parse_single(item, params)
        assert job.posted_at is not None
        assert job.posted_at.year == 2025

    def test_invalid_created_at_handled(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(created_at="not-a-date")
        job = source._parse_single(item, params)
        assert job.posted_at is None

    def test_remote_true(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(remote=True)
        job = source._parse_single(item, params)
        assert job.remote is True

    def test_country_code_from_params(self):
        source = ArbeitnowSource()
        params = SearchParams(country="AT")
        item = _make_api_item(country_code="")
        job = source._parse_single(item, params)
        assert job.location_country == "AT"

    def test_tags_as_string(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(tags="python")
        job = source._parse_single(item, params)
        assert job.tags == ["python"]

    def test_empty_tags(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item(tags=[])
        job = source._parse_single(item, params)
        assert job.tags is None

    def test_raw_data_stored(self):
        source = ArbeitnowSource()
        params = SearchParams()
        item = _make_api_item()
        job = source._parse_single(item, params)
        assert job.raw_data == item


class TestParseSalary:
    def test_range(self):
        result = ArbeitnowSource._parse_salary("50000 - 70000 EUR")
        assert result == (50000.0, 70000.0)

    def test_single_number(self):
        result = ArbeitnowSource._parse_salary("50000")
        assert result == (50000.0, None)

    def test_with_commas(self):
        result = ArbeitnowSource._parse_salary("50,000 - 70,000")
        assert result[0] == 50.0
        assert result[1] == 70.0

    def test_no_numbers(self):
        result = ArbeitnowSource._parse_salary("Competitive salary")
        assert result == (None, None)


class TestParseJobTypes:
    def test_full_time(self):
        types = ArbeitnowSource._parse_job_types({"job_type": "full-time"})
        assert "full-time" in types

    def test_part_time(self):
        types = ArbeitnowSource._parse_job_types({"job_type": "part-time"})
        assert "part-time" in types

    def test_contract(self):
        types = ArbeitnowSource._parse_job_types({"job_type": "contract"})
        assert "contract" in types

    def test_internship(self):
        types = ArbeitnowSource._parse_job_types({"job_type": "internship"})
        assert "internship" in types

    def test_remote_flag(self):
        types = ArbeitnowSource._parse_job_types({"remote": True})
        assert "remote" in types

    def test_empty_returns_none(self):
        types = ArbeitnowSource._parse_job_types({})
        assert types is None


class TestParseResults:
    def test_empty_data(self):
        source = ArbeitnowSource()
        params = SearchParams()
        assert source._parse_results({}, params) == []
        assert source._parse_results({"data": []}, params) == []

    def test_multiple_jobs(self):
        source = ArbeitnowSource()
        params = SearchParams()
        data = {"data": [_make_api_item(slug="a"), _make_api_item(slug="b")]}
        jobs = source._parse_results(data, params)
        assert len(jobs) == 2

    def test_skips_invalid_items(self):
        source = ArbeitnowSource()
        params = SearchParams()
        data = {
            "data": [_make_api_item(slug="a"), {"title": ""}, _make_api_item(slug="c")]
        }
        jobs = source._parse_results(data, params)
        assert len(jobs) == 2


class TestFetch:
    @patch("src.services.job_sources.arbeitnow.httpx.Client")
    def test_fetch_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [_make_api_item(slug="test-job")]}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitnowSource()
        params = SearchParams(query="Python", city="Berlin", country="DE")
        jobs = source.fetch(params)

        assert len(jobs) == 1
        assert jobs[0].source_id == "test-job"

    @patch("src.services.job_sources.arbeitnow.httpx.Client")
    def test_fetch_error_returns_empty(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitnowSource()
        params = SearchParams(query="Python")
        jobs = source.fetch(params)

        assert jobs == []
