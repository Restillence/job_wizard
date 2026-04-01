from src.services.llm_utils import call_llm


class PIIStrippingService:
    def strip_pii(self, text: str) -> str:
        prompt = (
            "You are a PII stripping service. "
            "Redact all names, email addresses, and phone numbers in the provided text. "
            "Replace each PII entity with the tag '[REDACTED]'. "
            "Return ONLY the redacted text. Do not include any explanations or other text.\n\n"
            f"Text: {text}"
        )
        return call_llm([{"role": "user", "content": prompt}])
