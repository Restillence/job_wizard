import re
from litellm import completion, acompletion, embedding
from src.config import settings


def _extract_content(response) -> str:
    msg = response.choices[0].message
    content = msg.content or ""
    if content.strip():
        return content.strip()
    rc = getattr(msg, "reasoning_content", None) or ""
    if isinstance(rc, str) and rc.strip():
        json_match = re.search(r"\{[\s\S]*\}", rc)
        if json_match:
            return json_match.group(0)
        json_arr_match = re.search(r"\[[\s\S]*\]", rc)
        if json_arr_match:
            return json_arr_match.group(0)
        return rc.strip()
    return ""


def call_llm(
    messages: list,
    *,
    model: str = "openai/glm-5.1",
    timeout: int = 120,
    max_tokens: int = 4096,
) -> str:
    response = completion(
        model=model,
        api_base=settings.ZAI_API_BASE,
        api_key=settings.ZAI_API_KEY,
        messages=messages,
        timeout=timeout,
        max_tokens=max_tokens,
    )
    return _extract_content(response)


async def acall_llm(
    messages: list,
    *,
    model: str = "openai/glm-5.1",
    timeout: int = 120,
    max_tokens: int = 4096,
) -> str:
    response = await acompletion(
        model=model,
        api_base=settings.ZAI_API_BASE,
        api_key=settings.ZAI_API_KEY,
        messages=messages,
        timeout=timeout,
        max_tokens=max_tokens,
    )
    return _extract_content(response)


def call_embedding(*args, **kwargs):
    return embedding(*args, **kwargs)
