from unittest.mock import patch
from src.services.job_sources import get_sources, search_all
from src.services.job_sources.base import BaseJobSource, NormalizedJob, SearchParams


class FakeSource(BaseJobSource):
    def __init__(self, name_str, countries, jobs=None):
        self._name = name_str
        self._countries = countries
        self._jobs = jobs or []

    @property
    def name(self):
        return self._name

    @property
    def supported_countries(self):
        return self._countries

    def fetch(self, params):
        return self._jobs


class TestGetSources:
    def test_returns_all_sources(self):
        sources = get_sources()
        assert len(sources) >= 2
        names = [s.name for s in sources]
        assert "arbeitsagentur" in names
        assert "arbeitnow" in names

    def test_filter_by_de(self):
        sources = get_sources(country="DE")
        names = [s.name for s in sources]
        assert "arbeitsagentur" in names
        assert "arbeitnow" in names

    def test_filter_by_at(self):
        sources = get_sources(country="AT")
        names = [s.name for s in sources]
        assert "arbeitsagentur" not in names
        assert "arbeitnow" in names

    def test_filter_by_ch(self):
        sources = get_sources(country="CH")
        names = [s.name for s in sources]
        assert "arbeitsagentur" not in names
        assert "arbeitnow" in names

    def test_filter_case_insensitive(self):
        sources = get_sources(country="de")
        names = [s.name for s in sources]
        assert "arbeitsagentur" in names


class TestSearchAll:
    @patch("src.services.job_sources._get_registry")
    def test_combines_results(self, mock_registry):
        job1 = NormalizedJob(
            title="Dev A",
            company_name="Corp A",
            source_url="http://a.com",
            source="source_a",
        )
        job2 = NormalizedJob(
            title="Dev B",
            company_name="Corp B",
            source_url="http://b.com",
            source="source_b",
        )

        mock_registry.return_value = [
            FakeSource("source_a", ["DE"], [job1]),
            FakeSource("source_b", ["DE"], [job2]),
        ]

        params = SearchParams(country="DE")
        results = search_all(params)

        assert len(results) == 2

    @patch("src.services.job_sources._get_registry")
    def test_deduplicates_across_sources(self, mock_registry):
        job1 = NormalizedJob(
            title="Python Dev",
            company_name="Corp",
            source_url="http://a.com",
            source="source_a",
            location_city="Berlin",
        )
        job2 = NormalizedJob(
            title="Python Dev",
            company_name="Corp",
            source_url="http://b.com",
            source="source_b",
            location_city="Berlin",
        )

        mock_registry.return_value = [
            FakeSource("source_a", ["DE"], [job1]),
            FakeSource("source_b", ["DE"], [job2]),
        ]

        params = SearchParams(country="DE")
        results = search_all(params)

        assert len(results) == 1

    @patch("src.services.job_sources._get_registry")
    def test_source_failure_continues(self, mock_registry):
        job1 = NormalizedJob(
            title="Dev A",
            company_name="Corp A",
            source_url="http://a.com",
            source="good_source",
        )

        class FailingSource(BaseJobSource):
            @property
            def name(self):
                return "failing"

            @property
            def supported_countries(self):
                return ["DE"]

            def fetch(self, params):
                raise Exception("API down")

        mock_registry.return_value = [
            FakeSource("good_source", ["DE"], [job1]),
            FailingSource(),
        ]

        params = SearchParams(country="DE")
        results = search_all(params)

        assert len(results) == 1
        assert results[0].title == "Dev A"

    @patch("src.services.job_sources._get_registry")
    def test_empty_results(self, mock_registry):
        mock_registry.return_value = [
            FakeSource("source_a", ["DE"], []),
            FakeSource("source_b", ["DE"], []),
        ]

        params = SearchParams(country="DE")
        results = search_all(params)

        assert results == []
