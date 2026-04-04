from unittest.mock import patch, MagicMock
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.base import SearchParams


def _make_api_item(**overrides):
    item = {
        "refnr": "10000000",
        "beruf": "Python Entwickler",
        "titel": "Senior Python Developer (m/w/d)",
        "arbeitgeber": "TestCorp GmbH",
        "arbeitsort": {
            "plz": "10115",
            "ort": "Berlin",
            "region": "Berlin",
            "land": "Deutschland",
            "koordinaten": {"lat": 52.52, "lon": 13.40},
        },
        "aktuelleVeroeffentlichungsdatum": "2025-01-15",
        "modifikationsTimestamp": "2025-01-15T10:00:00.000",
        "eintrittsdatum": "2025-01-15",
        "externeUrl": "https://example.com/job/10000000",
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

    def test_correct_search_url(self):
        assert (
            ArbeitsagenturSource.SEARCH_URL
            == "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs"
        )

    def test_no_oauth_attributes(self):
        source = ArbeitsagenturSource()
        assert not hasattr(source, "_token")
        assert not hasattr(source, "_token_lock")
        assert not hasattr(source, "_token_expires_at")
        assert not hasattr(source, "_get_access_token")
        assert not hasattr(source, "_invalidate_token")
        assert not hasattr(source, "TOKEN_URL")


class TestParseSingle:
    def test_basic_parsing(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)

        assert job is not None
        assert job.title == "Senior Python Developer (m/w/d)"
        assert job.company_name == "TestCorp GmbH"
        assert job.source == "arbeitsagentur"
        assert job.source_id == "10000000"
        assert job.location_city == "Berlin"
        assert job.location_region == "Berlin"
        assert job.location_country == "Deutschland"
        assert job.source_url == "https://example.com/job/10000000"

    def test_title_prefers_titel_over_beruf(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(titel="Software Engineer", beruf="Entwickler")
        job = source._parse_single(item)
        assert job.title == "Software Engineer"

    def test_title_fallback_to_beruf(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(titel="", beruf="Python Entwickler")
        job = source._parse_single(item)
        assert job.title == "Python Entwickler"

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

    def test_source_url_fallback(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(externeUrl="")
        job = source._parse_single(item)
        assert (
            job.source_url
            == "https://www.arbeitsagentur.de/jobsuche/jobdetail/10000000"
        )

    def test_source_url_uses_externe_url(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(externeUrl="https://gute-jobs.de/viewjob-abc")
        job = source._parse_single(item)
        assert job.source_url == "https://gute-jobs.de/viewjob-abc"

    def test_posted_at_parsing(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="2025-03-01")
        job = source._parse_single(item)
        assert job.posted_at is not None
        assert job.posted_at.year == 2025
        assert job.posted_at.month == 3

    def test_posted_at_iso_with_time(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="2025-03-01T12:30:00")
        job = source._parse_single(item)
        assert job.posted_at is not None
        assert job.posted_at.hour == 12

    def test_invalid_posted_at_handled(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="not-a-date")
        job = source._parse_single(item)
        assert job.posted_at is None

    def test_empty_posted_at_handled(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(aktuelleVeroeffentlichungsdatum="")
        job = source._parse_single(item)
        assert job.posted_at is None

    def test_raw_data_stored(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)
        assert job.raw_data == item

    def test_default_country_deutschland(self):
        source = ArbeitsagenturSource()
        item = _make_api_item()
        job = source._parse_single(item)
        assert job.location_country == "Deutschland"

    def test_missing_arbeitsort(self):
        source = ArbeitsagenturSource()
        item = _make_api_item(arbeitsort=None)
        job = source._parse_single(item)
        assert job is not None
        assert job.location_city == ""
        assert job.location_region == ""


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
    def test_fetch_sends_correct_headers(self, mock_client_cls):
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
        call_headers = mock_client.get.call_args[1]["headers"]
        assert call_headers["X-API-Key"] == "jobboerse-jobsuche"
        assert "rest.arbeitsagentur.de" in call_headers["Host"]

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_queries_all_angebotsarten(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stellenangebote": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", city="Berlin")
        source.fetch(params)

        assert mock_client.get.call_count == 3
        angebotsarten = [
            call[1]["params"]["angebotsart"] for call in mock_client.get.call_args_list
        ]
        assert sorted(angebotsarten) == [1, 4, 34]

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_merges_results_from_all_types(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        responses = [
            {"stellenangebote": [_make_api_item(refnr="job-1")]},
            {"stellenangebote": [_make_api_item(refnr="job-4")]},
            {"stellenangebote": [_make_api_item(refnr="job-34")]},
        ]
        mock_response.json.side_effect = responses
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", per_page=10)
        jobs = source.fetch(params)

        assert len(jobs) == 3
        refnrs = {j.source_id for j in jobs}
        assert refnrs == {"job-1", "job-4", "job-34"}

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_deduplicates_by_refnr(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        responses = [
            {"stellenangebote": [_make_api_item(refnr="dup-1")]},
            {"stellenangebote": [_make_api_item(refnr="dup-1")]},
            {"stellenangebote": [_make_api_item(refnr="unique-34")]},
        ]
        mock_response.json.side_effect = responses
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", per_page=10)
        jobs = source.fetch(params)

        assert len(jobs) == 2
        refnrs = {j.source_id for j in jobs}
        assert refnrs == {"dup-1", "unique-34"}

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_sends_correct_params(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stellenangebote": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", city="Berlin", page=2, per_page=50)
        source.fetch(params)

        call_params = mock_client.get.call_args[1]["params"]
        assert call_params["was"] == "Python"
        assert call_params["wo"] == "Berlin"
        assert call_params["page"] == 2
        assert call_params["size"] == 50

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_combines_keywords(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stellenangebote": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(keywords=["python", "django"])
        source.fetch(params)

        call_params = mock_client.get.call_args[1]["params"]
        assert call_params["was"] == "python django"

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_no_query_omits_was(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stellenangebote": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams()
        source.fetch(params)

        call_params = mock_client.get.call_args[1]["params"]
        assert "was" not in call_params

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

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_continues_on_single_type_error(self, mock_client_cls):
        mock_client = MagicMock()
        response_jobs = MagicMock()
        response_jobs.status_code = 200
        response_jobs.json.return_value = {
            "stellenangebote": [_make_api_item(refnr="survived")]
        }
        response_jobs.raise_for_status = MagicMock()

        response_error = MagicMock()
        response_error.status_code = 500
        response_error.raise_for_status.side_effect = Exception("Server error")

        response_jobs2 = MagicMock()
        response_jobs2.status_code = 200
        response_jobs2.json.return_value = {
            "stellenangebote": [_make_api_item(refnr="survived-2")]
        }
        response_jobs2.raise_for_status = MagicMock()

        mock_client.get.side_effect = [response_error, response_jobs, response_jobs2]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        params = SearchParams(query="Python", per_page=10)
        jobs = source.fetch(params)

        assert len(jobs) == 2
