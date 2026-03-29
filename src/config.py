from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./jobwiz_test.db"
    RUN_E2E_TESTS: bool = False

    # Z.ai Coding Plan (for LLM completions via LiteLLM)
    ZAI_API_KEY: Optional[str] = None
    ZAI_API_BASE: str = "https://api.z.ai/api/coding/paas/v4"

    # Gemini API Key for Embeddings (free tier)
    GEMINI_API_KEY: Optional[str] = None

    # Optional Search API Keys for Job Discovery Fallback
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    BRAVE_API_KEY: Optional[str] = None

    # OpenAI API Key for Embeddings (optional fallback)
    OPENAI_API_KEY: Optional[str] = None

    # Job Board API Keys
    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None
    JOOBLE_API_KEY: Optional[str] = None
    CAREERJET_AFFID: Optional[str] = None
    CACHE_TTL_SECONDS: int = 3600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def validate_required_keys(self) -> list[str]:
        missing = []
        if not self.ZAI_API_KEY:
            missing.append("ZAI_API_KEY")
        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        return missing


settings = Settings()
