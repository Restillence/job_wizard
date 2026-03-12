from typing import Any
import litellm
from src.config import settings

class PIIStrippingService:
    def strip_pii(self, text: str) -> str:
        prompt = (
            "You are a PII stripping service. "
            "Redact all names, email addresses, and phone numbers in the provided text. "
            "Replace each PII entity with the tag '[REDACTED]'. "
            "Return ONLY the redacted text. Do not include any explanations or other text.\n\n"
            f"Text: {text}"
        )
        response = litellm.completion(
            model="openai/glm-5",
            messages=[{"role": "user", "content": prompt}],
            api_base=settings.ZAI_API_BASE,
            api_key=settings.ZAI_API_KEY,
        )
        # Type hint for response.choices[0].message.content is tricky, 
        # but litellm returns a ModelResponse object
        return str(response.choices[0].message.content).strip()
