from typing import Optional
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

    # Groq API Configuration
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"


    # Document Normalization Pipeline Thresholds
    MAX_VERTICAL_GAP: float = 15.0
    INDENT_TOLERANCE: float = 5.0
    MERGE_SIMILARITY: float = 0.8
    HEADER_REPETITION_THRESHOLD: int = 2
    FOOTER_REPETITION_THRESHOLD: int = 2
    CROSS_PAGE_MERGE_ENABLED: bool = True
    HYPHEN_MERGE_ENABLED: bool = True
    HEADER_FOOTER_MODE: str = "remove"  # "remove" or "classify"

    @property
    def api_prefix(self) -> str:
        """Return the versioned API prefix."""
        return f"/api/{self.API_VERSION}"


settings = Settings()
