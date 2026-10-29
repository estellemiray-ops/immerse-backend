from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./immerse.db"
    groq_api_key: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30  # 30 days
    cors_origins: str = "*"
    groq_model: str = "qwen/qwen3-32b"  # strong Chinese quality, free tier, no card
    groq_whisper_model: str = "whisper-large-v3-turbo"  # hosted transcription, free tier, no card

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
