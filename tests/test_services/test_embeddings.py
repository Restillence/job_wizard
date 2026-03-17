from unittest.mock import patch, MagicMock
from src.services.embeddings import (
    generate_embedding,
    generate_job_embedding,
    generate_resume_embedding,
    cosine_similarity,
    embedding_to_json,
    json_to_embedding,
)


class TestEmbeddingFunctions:
    @patch("src.services.embeddings.settings")
    def test_generate_embedding_no_api_key(self, mock_settings):
        mock_settings.OPENAI_API_KEY = None
        result = generate_embedding("test text")
        assert result is None

    @patch("src.services.embeddings.get_openai_client")
    def test_generate_embedding_success(self, mock_client_factory):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response
        mock_client_factory.return_value = mock_client

        with patch("src.services.embeddings.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            result = generate_embedding("test text")

        assert result == [0.1, 0.2, 0.3]

    def test_generate_embedding_empty_text(self):
        result = generate_embedding("")
        assert result is None

        result = generate_embedding("   ")
        assert result is None

    @patch("src.services.embeddings.generate_embedding")
    def test_generate_job_embedding(self, mock_gen):
        mock_gen.return_value = [0.1, 0.2, 0.3]

        result = generate_job_embedding(
            title="Software Engineer",
            description="Build software",
            requirements={"skills": ["Python"]},
        )

        assert result == [0.1, 0.2, 0.3]
        mock_gen.assert_called_once()

    @patch("src.services.embeddings.generate_embedding")
    def test_generate_resume_embedding(self, mock_gen):
        mock_gen.return_value = [0.4, 0.5, 0.6]

        result = generate_resume_embedding(
            resume_text="Experienced developer",
            zusatz_infos={"skills": ["Python", "Docker"], "interests": ["AI"]},
        )

        assert result == [0.4, 0.5, 0.6]
        mock_gen.assert_called_once()


class TestCosineSimilarity:
    def test_cosine_similarity_identical(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        result = cosine_similarity(a, b)
        assert abs(result - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        result = cosine_similarity(a, b)
        assert abs(result) < 0.001

    def test_cosine_similarity_opposite(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        result = cosine_similarity(a, b)
        assert abs(result + 1.0) < 0.001

    def test_cosine_similarity_empty(self):
        result = cosine_similarity([], [1.0, 2.0])
        assert result == 0.0

        result = cosine_similarity([1.0, 2.0], [])
        assert result == 0.0

    def test_cosine_similarity_partial_match(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        result = cosine_similarity(a, b)
        assert 0.5 < result < 1.0


class TestEmbeddingSerialization:
    def test_embedding_to_json(self):
        embedding = [0.1, 0.2, 0.3]
        result = embedding_to_json(embedding)
        assert result == "[0.1, 0.2, 0.3]"

    def test_embedding_to_json_none(self):
        result = embedding_to_json(None)
        assert result is None

    def test_json_to_embedding(self):
        json_str = "[0.1, 0.2, 0.3]"
        result = json_to_embedding(json_str)
        assert result == [0.1, 0.2, 0.3]

    def test_json_to_embedding_none(self):
        result = json_to_embedding(None)
        assert result is None

    def test_json_to_embedding_invalid(self):
        result = json_to_embedding("not valid json")
        assert result is None
