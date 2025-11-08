import logging
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Self


class Settings(BaseSettings):
    """
    Manages application settings using environment variables.
    Settings are loaded from a .env file and environment variables.
    Settings that need to be exposed to the front-end need to be
    explicitly not excluded.
    """
    # Configure Pydantic to load from a .env file if it exists
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    # Application Options
    MOTOTWIST_INSTANCE_NAME: str = Field(default="MotoTwist", exclude=False)
    MOTOTWIST_BASE_URL: str = Field(default="http://localhost:8000", exclude=True)
    MOTOTWIST_SECRET_KEY: str = Field(default="mototwist", exclude=True)
    OSM_URL: str = Field(default="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", exclude=False)
    OSRM_URL: str = Field(default="https://router.project-osrm.org", exclude=False)
    TWIST_SIMPLIFICATION_TOLERANCE_M: int = Field(default=0, exclude=True)
    DEFAULT_TWISTS_LOADED: int = Field(default=20, gt=1, exclude=True)
    MAX_TWISTS_LOADED: int = Field(default=100, gt=1, exclude=True)
    RATINGS_FETCHED_PER_QUERY: int = Field(default=20, gt=1, exclude=True)

    # User Options
    MOTOTWIST_ADMIN_EMAIL: str = Field(default="admin@admin.com", exclude=True)
    MOTOTWIST_ADMIN_PASSWORD: str = Field(default="password", exclude=True)
    ALLOW_USER_REGISTRATION: bool = Field(default=False, exclude=False)
    DELETED_USER_NAME: str = Field(default="Deleted User", exclude=True)
    AUTH_COOKIE_MAX_AGE: int | None = Field(default=3600, ge=0, exclude=False)
    AUTH_SLIDING_WINDOW_ENABLED: bool = Field(default=True, exclude=True)
    AUTH_EXPIRY_WARNING_OFFSET: int = Field(default=300, ge=0, exclude=False)

    # Email Options
    EMAIL_ENABLED: bool = Field(default=False, exclude=False)
    SMTP_HOST: str = Field(default="", exclude=True)
    SMTP_PORT: int = Field(default=587, exclude=True)
    SMTP_USERNAME: str = Field(default="", exclude=True)
    SMTP_PASSWORD: str = Field(default="", exclude=True)
    SMTP_FROM_EMAIL: str = Field(default="", exclude=True)
    SMTP_USE_TLS: bool = Field(default=True, exclude=True)

    # Database Options
    POSTGRES_HOST: str = Field(default="db", exclude=True)
    POSTGRES_PORT: int = Field(default=5432, exclude=True)
    POSTGRES_DB: str = Field(default="mototwist", exclude=True)
    POSTGRES_USER: str = Field(default="mototwist", exclude=True)
    POSTGRES_PASSWORD: str = Field(default="password", exclude=True)

    REDIS_URL: str = Field(default="redis://redis:6379", exclude=True)

    # Developer Options
    LOG_LEVEL: str = Field(default="INFO", exclude=True)
    DEBUG_MODE: bool = Field(default=False, exclude=False)
    UVICORN_RELOAD: bool = Field(default=False, exclude=True)
    MOTOTWIST_UPSTREAM: str = Field(default="amot-dev/mototwist", exclude=False)

    # Do not change unless you want to be rate-limited by the GitHub API during development
    # This is set properly by GitHub Actions during the release flow
    MOTOTWIST_VERSION: str = Field(default="dev", exclude=False)


    # @computed_field - by dropping computed_field, this field is exclude=True
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """Construct the database URL from individual components."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validates that LOG_LEVEL is a valid Python logging level."""
        # Get valid log levels directly from the logging module
        valid_levels = list(logging.getLevelNamesMapping().keys())

        upper_value = value.upper()
        if upper_value not in valid_levels:
            raise ValueError(
                f"Invalid LOG_LEVEL: '{value}'"
                f"Must be one of {valid_levels}"
            )
        return upper_value

    @field_validator("MOTOTWIST_BASE_URL")
    @classmethod
    def remove_trailing_slash_from_base_url(cls, value: str) -> str:
        """Removes the trailing slash from the base URL."""
        return value.rstrip("/")

    @field_validator("TWIST_SIMPLIFICATION_TOLERANCE_M", mode="before")
    @classmethod
    def parse_tolerance_from_string(cls, value: Any) -> int:
        """Parses an integer from a string like '10m' or '25'."""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip().rstrip("mM"))
            except (ValueError, TypeError):
                raise ValueError(f"Invalid tolerance value: '{value}'")
        raise TypeError("Tolerance value must be a string or integer")

    @field_validator("AUTH_COOKIE_MAX_AGE", mode="after")
    @classmethod
    def to_session_cookie(cls, v: int | None) -> int | None:
        if not v:
            return None

        return v

    @model_validator(mode='after')
    def check_default_twists_loaded_against_max(self) -> Self:
        if self.DEFAULT_TWISTS_LOADED > self.MAX_TWISTS_LOADED:
            raise ValueError(
                f"DEFAULT_TWISTS_LOADED ({self.DEFAULT_TWISTS_LOADED}) must be less than or equal to MAX_TWISTS_LOADED ({self.MAX_TWISTS_LOADED})"
            )
        return self

    @model_validator(mode='after')
    def check_auth_expiry_warning_offset_against_max(self) -> Self:
        auth_cookie_max_age = self.AUTH_COOKIE_MAX_AGE if self.AUTH_COOKIE_MAX_AGE else 0
        if self.AUTH_EXPIRY_WARNING_OFFSET > auth_cookie_max_age:
            raise ValueError(
                f"AUTH_EXPIRY_WARNING_OFFSET ({self.AUTH_EXPIRY_WARNING_OFFSET}) must be less than or equal to AUTH_COOKIE_MAX_AGE ({auth_cookie_max_age})"
            )
        return self


# Create a single importable instance of settings (or error)
try:
    settings = Settings()
except ValidationError as e:
    error_message: str = f"Found {e.error_count()} .env error(s):"
    for error in e.errors():
        error_message += f"\n  - {error["msg"]}"

    logging.getLogger("mototwist").error(error_message)
    exit(1)