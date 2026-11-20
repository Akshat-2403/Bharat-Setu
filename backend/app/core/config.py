import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "bharatsetu.db"
DEFAULT_UPLOAD_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../uploads")))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore", env_file=".env")

    PROJECT_NAME: str = "BharatSetu Bid Compliance Verification Platform"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"
    JWT_SECRET_KEY: str = Field(default="development-only-change-this-secret", min_length=1)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DATABASE_URL: str | None = None
    UPLOAD_DIR: str = str(DEFAULT_UPLOAD_DIR)
    MAX_FILE_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_EXTENSIONS: set[str] = {".pdf", ".png", ".jpg", ".jpeg"}

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    VERIFICATION_MODE: str = "mock"
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    OCR_ENABLED: bool = True
    ENABLE_DEMO_SEED: bool = False

    EMAIL_NOTIFICATIONS_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    NOTIFICATION_FROM_EMAIL: str = ""
    SMS_NOTIFICATIONS_ENABLED: bool = False
    SMS_PROVIDER: str = "mock"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    NOTIFICATION_TIME_ZONE: str = "UTC"
    NOTIFICATION_ACTION_URL: str = ""
    DEADLINE_REMINDER_INTERVAL_SECONDS: int = 60

    @model_validator(mode="after")
    def validate_deployment_settings(self):
        production = self.ENVIRONMENT.strip().lower() == "production"
        if not self.DATABASE_URL:
            if production:
                raise ValueError("DATABASE_URL is required when ENVIRONMENT=production")
            self.DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"
        elif self.DATABASE_URL.startswith(("postgres://", "postgresql://")):
            scheme = "postgresql+psycopg://"
            self.DATABASE_URL = scheme + self.DATABASE_URL.split("://", 1)[1]
        if production:
            if "ENABLE_DEMO_SEED" not in os.environ:
                raise ValueError("ENABLE_DEMO_SEED must be explicitly set in production")
            if not os.getenv("CORS_ORIGINS", "").strip():
                raise ValueError("CORS_ORIGINS is required when ENVIRONMENT=production")
            if self.JWT_SECRET_KEY == "development-only-change-this-secret":
                raise ValueError("JWT_SECRET_KEY is required when ENVIRONMENT=production")
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
            if not self.DATABASE_URL.startswith("postgresql+psycopg://"):
                raise ValueError("Production DATABASE_URL must point to PostgreSQL")
        return self

    @property
    def SECRET_KEY(self) -> str:
        return self.JWT_SECRET_KEY

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
