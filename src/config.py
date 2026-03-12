from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./jobwiz_test.db"
    ZAI_API_KEY: str = "10961f6dcd11491596cb665061971d99.VGiyR7D0E9Oo83hz"
    ZAI_API_BASE: str = "https://api.z.ai/api/coding/paas/v4"


settings = Settings()
