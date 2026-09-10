import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "Financial Document Intelligence Platform"
    API_V1_STR: str = "/api/v1"
    
    # Security & API
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    
    # Database
    DATABASE_URL: str = "sqlite:///./financial_docs.db"
    
    # Upload limits
    MAX_FILE_SIZE_MB: int = 10
    
    # Validation engine tolerances
    VALIDATION_ABSOLUTE_TOLERANCE: float = 1.0
    VALIDATION_RELATIVE_TOLERANCE: float = 0.01
    
    # App environment
    ENVIRONMENT: str = "development"

    @field_validator("GROQ_API_KEY", mode="after")
    @classmethod
    def clean_api_key(cls, v: str) -> str:
        if not v:
            return ""
        # Strip surrounding quotes and whitespace
        cleaned = v.strip().strip("'\"").strip()
        # Ignore obvious placeholder strings
        if cleaned.lower() in ("your_groq_api_key_here", "your_api_key_here", "your_api_key", "your_groq_api_key", "changeme"):
            return ""
        return cleaned

    @property
    def is_groq_api_key_configured(self) -> bool:
        """Returns True if a non-empty, non-placeholder Groq API key is set."""
        return bool(self.GROQ_API_KEY and len(self.GROQ_API_KEY) > 10)

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
