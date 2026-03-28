from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.base import SearchParams


def _make_api_item(**overrides):
    item = {
        "refnr": "10000000",
        "beruf": "Python Entwickler",
        "titel": "",
        "arbeitgeber": "TestCorp GmbH",
        "arbeitsort": {
            "ort": "Berlin",
            "region": "Berlin",
            "land": "DE",
        },
        "stellenbeschreibung": "Build Python apps",
        "aufgaben": "Develop backend services",
        "anforderungen": "Python, FastAPI",
        "aktuelleVeroeffentlichungsdatum": "2025-01-15T00:00:00",
        "homeOfficeMoglich": "true",
        "befristung": "unbefristet",
        "arbeitszeit": "Vollzeit",
    }
    item.update(overrides)
    return item


class TestArbeitsagenturSource:
    def test_name(self):
        source = ArbeitsagenturSource()
        assert source.name == "arbeitsagentur"

    def test_supported_countries(self):
        source = ArbeitsagenturSource()
        assert source.supported_countries == ["DE"]


class TestParseSingle:
    def test_basic_parsing(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)

        assert job is not None
        assert job.title == "Python Entwickler"
        assert job.company_name == "TestCorp GmbH"
        assert job.source == "arbeitsagentur"
        assert job.source_id == "10000000"
        assert job.location_city == "Berlin"
        assert job.location_region == "Berlin"
        assert job.location_country == "DE"
        assert job.remote is True
        assert "permanent" in (job.job_types or [])
        assert "full-time" in (job.job_types or [])
        assert (
            job.source_url
            == "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000000"
        )

    def test_no_refnr_returns_none(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(refnr="")
        assert source._parse_single(item) is None

    def test_no_title_returns_none(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(beruf="", titel="")
        assert source._parse_single(item) is None

    def test_no_company_returns_none(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(arbeitgeber="")
        assert source._parse_single(item) is None

    def test_title_fallback_to_titel(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(beruf="", titel="Software Engineer")
        job = source._parse_single(item)
        assert job.title == "Software Engineer"

    def test_description_concatenation(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)
        assert "Build Python apps" in job.description
        assert "Aufgaben: Develop backend services" in job.description
        assert "Anforderungen: Python, FastAPI" in job.description

    def test_posted_at_parsing(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="2025-03-01T12:00:00")
        job = source._parse_single(item)
        assert job.posted_at is not None
        assert job.posted_at.year == 2025
        assert job.posted_at.month == 3

    def test_invalid_posted_at_handled(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="not-a-date")
        job = source._parse_single(item)
        assert job.posted_at is None

    def test_remote_false(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(homeOfficeMoglich="false")
        job = source._parse_single(item)
        assert job.remote is False

    def test_raw_data_stored(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)
        assert job.raw_data == item


class TestParseJobTypes:
    def test_permanent_full_time(self):
        item = {"befristung": "unbefristet", "arbeitszeit": "Vollzeit"}
        types = ArbeitsagenturSource._parse_job_types(item)
        assert "permanent" in types
        assert "full-time" in types

    def test_temporary_part_time(self):
        item = {"befristung": "12 Monate", "arbeitszeit": "Teilzeit"}
        types = ArbeitsagenturSource._parse_job_types(item)
        assert "temporary" in types
        assert "part-time" in types

    def test_both_full_and_part(self):
        item = {"arbeitszeit": "Vollzeit/Teilzeit"}
        types = ArbeitsagenturSource._parse_job_types(item)
        assert "full-time" in types
        assert "part-time" in types

    def test_empty_returns_none(self):
        types = ArbeitsagenturSource._parse_job_types({})
        assert types is None


class TestParseResults:
    def test_empty_data(self):
        source = ArbeitsagenturSource()
        assert source._parse_results({}) == []
        assert source._parse_results({"stellenangebote": []}) == []

    def test_multiple_jobs(self):
        source = ArbeitsagenturSource()
        data = {
            "stellenangebote": [
                _make_api_item(refnr="1"),
                _make_api_item(refnr="2"),
            ]
        }
        jobs = source._parse_results(data)
        assert len(jobs) == 2

    def test_skips_invalid_items(self):
        source = ArbeitsagenturSource()
        data = {
            "stellenangebote": [
                _make_api_item(refnr="1"),
                {"refnr": ""},
                _make_api_item(refnr="3"),
            ]
        }
        jobs = source._parse_results(data)
        assert len(jobs) == 2


class TestFetch:
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stellenangebote": [_make_api_item(refnr="100")]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", city="Berlin")
        jobs = source.fetch(params)

        assert len(jobs) == 1
        assert jobs[0].source_id == "100"

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_error_returns_empty(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python")
        jobs = source.fetch(params)

        assert jobs == []
