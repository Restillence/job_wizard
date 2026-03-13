from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./jobwiz_test.db"
    ZAI_API_KEY: str = "10961f6dcd11491596cb665061971d99.VGiyR7D0E9Oo83hz"
    ZAI_API_BASE: str = "https://api.z.ai/api/coding/paas/v4"
    RUN_E2E_TESTS: bool = False
    
    # Optional Search API Keys for Job Discovery Fallback
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    BRAVE_API_KEY: Optional[str] = None
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
