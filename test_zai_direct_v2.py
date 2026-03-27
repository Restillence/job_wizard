from litellm import completion
from src.config import settings
import logging

try:
    print(f"Testing Z.ai API with base: {settings.ZAI_API_BASE}")
    response = completion(
        model="glm-5",
        custom_llm_provider="openai",
        api_base=settings.ZAI_API_BASE,
        api_key=settings.ZAI_API_KEY,
        messages=[{"role": "user", "content": "Hello"}],
    )
    print("Success!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed: {type(e).__name__}: {e}")
