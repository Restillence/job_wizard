from datetime import datetime
from unittest.mock import patch, MagicMock
from src.services.job_sources.arbeitnow import ArbeitnowSource
from src.services.job_sources.base import NormalizedJob, SearchParams


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
        item = _make_api_item()
        job = source._parse_single(item)

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
        item = _make_api_item(url="", slug="")
        assert source._parse_single(item) is None

    def test_slug_used_as_url_fallback(self):
        source = ArbeitnowSource()
        item = _make_api_item(url="")
        job = source._parse_single(item)
        assert (
            job.source_url
            == "https://www.arbeitnow.com/jobs/python-dev-testcorp-berlin"
        )

    def test_no_title_returns_none(self):
        source = ArbeitnowSource()
        item = _make_api_item(title="")
        assert source._parse_single(item) is None

    def test_no_company_returns_none(self):
        source = ArbeitnowSource()
        item = _make_api_item(company_name="")
        assert source._parse_single(item) is None

    def test_created_at_integer_timestamp(self):
        source = ArbeitnowSource()
        item = _make_api_item(created_at=1705312800)
        job = source._parse_single(item)
        assert job.posted_at is not None
        assert isinstance(job.posted_at, datetime)

    def test_created_at_string_iso(self):
        source = ArbeitnowSource()
        item = _make_api_item(created_at="2025-03-01T12:00:00Z")
        job = source._parse_single(item)
        assert job.posted_at is not None
        assert job.posted_at.year == 2025

    def test_invalid_created_at_handled(self):
        source = ArbeitnowSource()
        item = _make_api_item(created_at="not-a-date")
        job = source._parse_single(item)
        assert job.posted_at is None

    def test_remote_true(self):
        source = ArbeitnowSource()
        item = _make_api_item(remote=True)
        job = source._parse_single(item)
        assert job.remote is True

    def test_empty_country_code(self):
        source = ArbeitnowSource()
        item = _make_api_item(country_code="")
        job = source._parse_single(item)
        assert job.location_country == ""

    def test_tags_as_string(self):
        source = ArbeitnowSource()
        item = _make_api_item(tags="python")
        job = source._parse_single(item)
        assert job.tags == ["python"]

    def test_empty_tags(self):
        source = ArbeitnowSource()
        item = _make_api_item(tags=[])
        job = source._parse_single(item)
        assert job.tags is None

    def test_raw_data_stored(self):
        source = ArbeitnowSource()
        item = _make_api_item()
        job = source._parse_single(item)
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


class TestMatchesCountry:
    def test_no_country_filter_passes(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Berlin",
            location_country="DE",
        )
        assert ArbeitnowSource._matches_country(job, SearchParams()) is True

    def test_country_code_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_country="DE",
        )
        assert ArbeitnowSource._matches_country(job, SearchParams(country="DE")) is True

    def test_country_keyword_in_location(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Berlin, Germany",
            location_country="",
        )
        assert ArbeitnowSource._matches_country(job, SearchParams(country="DE")) is True

    def test_country_no_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="London, UK",
            location_country="GB",
        )
        assert (
            ArbeitnowSource._matches_country(job, SearchParams(country="DE")) is False
        )

    def test_austria_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Vienna, Austria",
            location_country="",
        )
        assert ArbeitnowSource._matches_country(job, SearchParams(country="AT")) is True

    def test_switzerland_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Zurich, Schweiz",
            location_country="",
        )
        assert ArbeitnowSource._matches_country(job, SearchParams(country="CH")) is True


class TestMatchesCity:
    def test_no_city_filter_passes(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Munich",
        )
        assert ArbeitnowSource._matches_city(job, SearchParams()) is True

    def test_city_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Berlin, Germany",
        )
        assert ArbeitnowSource._matches_city(job, SearchParams(city="Berlin")) is True

    def test_city_no_match(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Munich, Germany",
        )
        assert ArbeitnowSource._matches_city(job, SearchParams(city="Berlin")) is False


class TestMatchesText:
    def test_no_query_passes(self):
        job = NormalizedJob(
            title="Dev",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            description="Java developer",
        )
        assert ArbeitnowSource._matches_text(job, SearchParams()) is True

    def test_query_in_title(self):
        job = NormalizedJob(
            title="Python Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
        )
        assert ArbeitnowSource._matches_text(job, SearchParams(query="Python")) is True

    def test_query_in_description(self):
        job = NormalizedJob(
            title="Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            description="Work with Django and Python",
        )
        assert ArbeitnowSource._matches_text(job, SearchParams(query="Python")) is True

    def test_keyword_match(self):
        job = NormalizedJob(
            title="Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            description="We use React",
        )
        assert (
            ArbeitnowSource._matches_text(job, SearchParams(keywords=["react"])) is True
        )

    def test_no_match(self):
        job = NormalizedJob(
            title="Java Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            description="Enterprise Java development",
        )
        assert ArbeitnowSource._matches_text(job, SearchParams(query="Python")) is False

    def test_any_word_matches(self):
        job = NormalizedJob(
            title="Full Stack Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            description="Build web apps",
        )
        assert (
            ArbeitnowSource._matches_text(job, SearchParams(query="python developer"))
            is True
        )


class TestMatches:
    def test_all_filters_pass(self):
        job = NormalizedJob(
            title="Python Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Berlin, Germany",
            location_country="DE",
            description="Build things with Python",
        )
        params = SearchParams(query="Python", city="Berlin", country="DE")
        assert ArbeitnowSource._matches(job, params) is True

    def test_country_filter_rejects(self):
        job = NormalizedJob(
            title="Python Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="London, UK",
            location_country="GB",
        )
        params = SearchParams(query="Python", country="DE")
        assert ArbeitnowSource._matches(job, params) is False

    def test_city_filter_rejects(self):
        job = NormalizedJob(
            title="Python Developer",
            company_name="Corp",
            source_url="http://x.com",
            source="test",
            location_city="Munich, Germany",
            location_country="DE",
        )
        params = SearchParams(query="Python", city="Berlin", country="DE")
        assert ArbeitnowSource._matches(job, params) is False


class TestFetch:
    @patch("src.services.job_sources.arbeitnow.httpx.Client")
    def test_fetch_no_filters_returns_first_page(self, mock_client_cls):
        resp1 = MagicMock()
        resp1.json.return_value = {"data": [_make_api_item(slug="a")]}
        resp1.raise_for_status = MagicMock()
        resp2 = MagicMock()
        resp2.json.return_value = {"data": []}
        resp2.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.side_effect = [resp1, resp2]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitnowSource()
        params = SearchParams()
        jobs = source.fetch(params)

        assert len(jobs) == 1
        assert mock_client.get.call_count == 2

    @patch("src.services.job_sources.arbeitnow.httpx.Client")
    def test_fetch_multi_page_when_filtering(self, mock_client_cls):
        page1_data = [
            _make_api_item(
                slug="uk-job",
                location="London, UK",
                country_code="GB",
            )
        ]
        page2_data = [
            _make_api_item(
                slug="de-job",
                location="Berlin, Germany",
                country_code="DE",
            )
        ]

        resp1 = MagicMock()
        resp1.json.return_value = {"data": page1_data}
        resp1.raise_for_status = MagicMock()
        resp2 = MagicMock()
        resp2.json.return_value = {"data": page2_data}
        resp2.raise_for_status = MagicMock()
        resp3 = MagicMock()
        resp3.json.return_value = {"data": []}
        resp3.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.side_effect = [resp1, resp2, resp3]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitnowSource()
        params = SearchParams(country="DE")
        jobs = source.fetch(params)

        assert len(jobs) == 1
        assert jobs[0].source_id == "de-job"
        assert mock_client.get.call_count == 3
