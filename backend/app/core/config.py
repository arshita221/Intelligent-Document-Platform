from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Financial Document Intelligence Platform"
    API_V1_STR: str = "/api/v1"
    
    # Security & API
    GEMINI_API_KEY: str = ""
    
    # Database
    DATABASE_URL: str = "sqlite:///./financial_docs.db"
    
    # Upload limits
    MAX_FILE_SIZE_MB: int = 10
    
    # Validation engine tolerances
    VALIDATION_ABSOLUTE_TOLERANCE: float = 1.0
    VALIDATION_RELATIVE_TOLERANCE: float = 0.01
    
    # App environment
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
