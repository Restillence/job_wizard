import json
from typing import List, Optional
import numpy as np
from litellm import embedding
from src.config import settings

GEMINI_EMBEDDING_MODEL = "gemini/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 3072


def generate_embedding(text: str) -> Optional[List[float]]:
    if not text or not text.strip():
        return None

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required for embedding generation")

    try:
        response = embedding(
            model=GEMINI_EMBEDDING_MODEL,
            input=text[:8000],
            api_key=settings.GEMINI_API_KEY,
        )
        return list(response.data[0]["embedding"])
    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding: {e}")


def generate_job_embedding(
    title: str,
    description: str,
    requirements: dict,
    benefits: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Optional[List[float]]:
    combined_text = f"""
    Title: {title}
    
    Description: {description}
    
    Requirements: {json.dumps(requirements)}
    
    Benefits: {json.dumps(benefits) if benefits else "Not specified"}
    
    Tags: {", ".join(tags) if tags else ""}
    """
    return generate_embedding(combined_text)


def generate_resume_embedding(
    resume_text: str, zusatz_infos: dict
) -> Optional[List[float]]:
    skills = zusatz_infos.get("skills", [])
    interests = zusatz_infos.get("interests", [])

    combined_text = f"""
    Resume: {resume_text}
    
    Skills: {", ".join(skills) if skills else "Not specified"}
    
    Interests: {", ".join(interests) if interests else "Not specified"}
    """
    return generate_embedding(combined_text)


def cosine_similarity(embedding_a: List[float], embedding_b: List[float]) -> float:
    if not embedding_a or not embedding_b:
        return 0.0

    a = np.array(embedding_a)
    b = np.array(embedding_b)

    if a.shape != b.shape:
        return 0.0

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def embedding_to_json(embedding: Optional[List[float]]) -> Optional[str]:
    if embedding is None:
        return None
    return json.dumps(embedding)


def json_to_embedding(json_str: Optional[str]) -> Optional[List[float]]:
    if json_str is None:
        return None
    if isinstance(json_str, list):
        return json_str
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None
