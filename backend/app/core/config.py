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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=60)

    DATABASE_URL: str | None = None
    UPLOAD_DIR: str = str(DEFAULT_UPLOAD_DIR)
    STORAGE_BACKEND: str = "local"
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET_NAME: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_REGION: str = ""
    MAX_FILE_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_EXTENSIONS: set[str] = {".pdf", ".png", ".jpg", ".jpeg"}

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    VERIFICATION_MODE: str = "mock"
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=300)
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
        self.LLM_PROVIDER = self.LLM_PROVIDER.strip().lower()
        if self.LLM_PROVIDER not in {"mock", "gemini"}:
            raise ValueError("LLM_PROVIDER must be mock or gemini")
        if production and self.LLM_PROVIDER != "gemini":
            raise ValueError("LLM_PROVIDER=gemini is required when ENVIRONMENT=production")
        if self.LLM_PROVIDER == "gemini" and not self.GEMINI_API_KEY.strip():
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.LLM_PROVIDER == "gemini" and not self.GEMINI_MODEL.strip():
            raise ValueError("GEMINI_MODEL cannot be empty when LLM_PROVIDER=gemini")
        self.STORAGE_BACKEND = self.STORAGE_BACKEND.strip().lower()
        if self.STORAGE_BACKEND not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be local or s3")
        if production and self.STORAGE_BACKEND != "s3":
            raise ValueError("STORAGE_BACKEND=s3 is required when ENVIRONMENT=production")
        if self.STORAGE_BACKEND == "s3":
            missing = [name for name in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_REGION") if not getattr(self, name).strip()]
            if missing:
                raise ValueError(f"S3 storage configuration is missing: {', '.join(missing)}")
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
if settings.STORAGE_BACKEND == "local":
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
