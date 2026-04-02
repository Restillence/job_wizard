from unittest.mock import MagicMock, patch
from src.services.pii_stripping import PIIStrippingService


@patch("src.services.pii_stripping.call_llm")
def test_strip_pii(mock_call_llm: MagicMock) -> None:
    mock_call_llm.return_value = "Hello [REDACTED]!"

    service = PIIStrippingService()
    result = service.strip_pii("Hello John!")

    assert result == "Hello [REDACTED]!"
    mock_call_llm.assert_called_once()

    args, kwargs = mock_call_llm.call_args
    assert "John" in args[0][0]["content"]
