from unittest.mock import patch, MagicMock
from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.base import NormalizedJob


MOCK_HTML_WITH_JOBDETAIL = """
<html>
<body>
<script type="text/javascript">transferCache={"jobdetail":{"stellenangebotsBeschreibung":"&lt;p&gt;We are looking for a Senior Python Developer to join our team. You will work on backend services using FastAPI and PostgreSQL.&lt;/p&gt;","stellenangebotsTitel":"Senior Python Developer","firma":"TestCorp GmbH","homeofficemoeglich":true,"referenznummer":"10000-1234567890-S","stellenlokationen":[{"ort":"Berlin","region":"Berlin","land":"Deutschland"}]}}</script>
</body>
</html>
"""

MOCK_HTML_NO_JOBDETAIL = """
<html>
<body>
<script type="text/javascript">transferCache={"otherKey":"value"}</script>
</body>
</html>
"""

MOCK_HTML_NO_SCRIPTS = "<html><body><p>No scripts here</p></body></html>"


class TestFetchDetail:
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_detail_extracts_description(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = MOCK_HTML_WITH_JOBDETAIL

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        result = source.fetch_detail("10000-1234567890-S")

        assert result is not None
        assert "stellenangebotsBeschreibung" in result
        assert "Senior Python Developer" in result["stellenangebotsBeschreibung"]
        assert result["firma"] == "TestCorp GmbH"
        assert result["homeofficemoeglich"] is True

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_detail_returns_none_on_404(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        result = source.fetch_detail("nonexistent-refnr")

        assert result is None

    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_fetch_detail_returns_none_on_no_scripts(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = MOCK_HTML_NO_SCRIPTS

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        result = source.fetch_detail("10000-0000000000-S")

        assert result is None


class TestExtractJobdetailJson:
    def test_parses_embedded_json(self):
        source = ArbeitsagenturSource()
        result = source._extract_jobdetail_json(MOCK_HTML_WITH_JOBDETAIL)

        assert result is not None
        assert result["firma"] == "TestCorp GmbH"
        assert result["homeofficemoeglich"] is True

    def test_returns_none_when_no_jobdetail_key(self):
        source = ArbeitsagenturSource()
        result = source._extract_jobdetail_json(MOCK_HTML_NO_JOBDETAIL)

        assert result is None

    def test_returns_none_for_empty_html(self):
        source = ArbeitsagenturSource()
        result = source._extract_jobdetail_json("")

        assert result is None

    def test_returns_none_for_malformed_json(self):
        html = "<script>var x = {jobdetail: {broken json here</script>"
        source = ArbeitsagenturSource()
        result = source._extract_jobdetail_json(html)

        assert result is None


class TestEnrichJobs:
    @patch("src.services.job_sources.arbeitsagentur.time.sleep")
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_enrich_jobs_backfills_description(self, mock_client_cls, mock_sleep):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = MOCK_HTML_WITH_JOBDETAIL

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        jobs = [
            NormalizedJob(
                title="Dev",
                company_name="TestCorp",
                source_url="https://example.com/1",
                source="arbeitsagentur",
                source_id="10000-1234567890-S",
                description=None,
            )
        ]

        enriched = source.enrich_jobs(jobs)

        assert enriched[0].description is not None
        assert "Senior Python Developer" in enriched[0].description
        assert enriched[0].remote is True
        mock_sleep.assert_called_with(0.2)

    @patch("src.services.job_sources.arbeitsagentur.time.sleep")
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_enrich_jobs_skips_no_source_id(self, mock_client_cls, mock_sleep):
        source = ArbeitsagenturSource()
        jobs = [
            NormalizedJob(
                title="Dev",
                company_name="Corp",
                source_url="https://example.com/1",
                source="arbeitnow",
                source_id=None,
            )
        ]

        enriched = source.enrich_jobs(jobs)

        assert enriched[0].description is None
        mock_sleep.assert_not_called()

    @patch("src.services.job_sources.arbeitsagentur.time.sleep")
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_enrich_jobs_keeps_longer_description(self, mock_client_cls, mock_sleep):
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        source = ArbeitsagenturSource()
        jobs = [
            NormalizedJob(
                title="Dev",
                company_name="Corp",
                source_url="https://example.com/1",
                source="arbeitsagentur",
                source_id="10000-9999999999-S",
                description="Existing longer description that should be kept",
            )
        ]

        enriched = source.enrich_jobs(jobs)

        assert "Existing longer" in enriched[0].description

    @patch("src.services.job_sources.arbeitsagentur.time.sleep")
    @patch("src.services.job_sources.arbeitsagentur.httpx.Client")
    def test_enrich_jobs_handles_empty_list(self, mock_client_cls, mock_sleep):
        source = ArbeitsagenturSource()
        enriched = source.enrich_jobs([])

        assert enriched == []
