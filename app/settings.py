import logging
from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Self


class Settings(BaseSettings):
    """
    Manages application settings using environment variables.
    Settings are loaded from a .env file and environment variables.
    """
    # Configure Pydantic to load from a .env file if it exists
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    # Application Options
    MOTOTWIST_BASE_URL: str = "http://localhost:8000"
    MOTOTWIST_SECRET_KEY: str = "mototwist"
    OSM_URL: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    OSRM_URL: str = "https://router.project-osrm.org"
    TWIST_SIMPLIFICATION_TOLERANCE_M: int = Field(default=0)
    DEFAULT_TWISTS_LOADED: int = Field(default=20, gt=1)
    MAX_TWISTS_LOADED: int = Field(default=100, gt=1)

    # User Options
    MOTOTWIST_ADMIN_EMAIL: str = "admin@admin.com"
    MOTOTWIST_ADMIN_PASSWORD: str = "password"
    ALLOW_USER_REGISTRATION: bool = False
    DELETED_USER_NAME: str = "Deleted User"

    # Database Options
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "mototwist"
    POSTGRES_USER: str = "mototwist"
    POSTGRES_PASSWORD: str = "password"

    REDIS_URL: str = "redis://redis:6379"

    # Developer Options
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False
    UVICORN_RELOAD: bool = False
    MOTOTWIST_UPSTREAM: str = "amot-dev/mototwist"

    # Do not change unless you want to be rate-limited by the GitHub API during development
    # This is set properly by GitHub Actions during the release flow
    MOTOTWIST_VERSION: str = "dev"


    @computed_field
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

    @model_validator(mode='after')
    def check_max_gt_default(self) -> Self:
        if self.DEFAULT_TWISTS_LOADED > self.MAX_TWISTS_LOADED:
            raise ValueError(
                f"DEFAULT_TWISTS_LOADED ({self.DEFAULT_TWISTS_LOADED}) must be less than MAX_TWISTS_LOADED ({self.MAX_TWISTS_LOADED})"
            )
        return self


# Create a single, importable instance of the settings
settings = Settings()