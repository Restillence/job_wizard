from unittest.mock import MagicMock, patch
from src.services.pii_stripping import PIIStrippingService


@patch("litellm.completion")
def test_strip_pii(mock_completion: MagicMock) -> None:
    # Configure mock
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello [REDACTED]!"))]
    mock_completion.return_value = mock_response

    service = PIIStrippingService()
    result = service.strip_pii("Hello John!")

    assert result == "Hello [REDACTED]!"
    mock_completion.assert_called_once()

    # Verify call parameters
    args, kwargs = mock_completion.call_args
    assert kwargs["model"] == "openai/glm-5"
    assert "John" in kwargs["messages"][0]["content"]
