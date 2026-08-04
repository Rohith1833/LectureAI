from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    PROJECT_NAME: str = "LectureAI"
    API_VERSION: str = "v1"
    DATABASE_URL: str = "sqlite:///./lectureai.db"

    @property
    def api_prefix(self) -> str:
        """Return the versioned API prefix."""
        return f"/api/{self.API_VERSION}"


settings = Settings()
