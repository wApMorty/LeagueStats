"""Configuration module for LeagueStats Coach API Server.

This module loads configuration from environment variables using pydantic-settings.
All sensitive configuration (DATABASE_URL, API keys, etc.) should be stored in .env file.

Example .env file:
    DATABASE_URL=postgresql://user:pass@host/db
    API_HOST=0.0.0.0
    API_PORT=8000
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        database_url: PostgreSQL connection string (from DATABASE_URL env var)
        api_host: API server host (default: 0.0.0.0)
        api_port: API server port (default: 8000)
        cors_origins: Comma-separated list of allowed CORS origins
        log_level: Logging level (default: INFO)
        app_version: Application version
        app_env: Application environment (development/production)
    """

    # Database
    database_url: str

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "*"

    # Logging
    log_level: str = "INFO"

    # Application
    app_version: str = "2.0.0"
    app_env: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list.

        Returns:
            List of allowed CORS origin URLs
        """
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def get_async_database_url(self) -> str:
        """Get asyncpg-compatible database URL.

        Converts psycopg-style connection string (sslmode=require) to asyncpg format.
        asyncpg doesn't support sslmode parameter, SSL is handled differently.

        Returns:
            Database URL compatible with asyncpg (with +asyncpg driver)
        """
        url = self.database_url

        # Remove sslmode and channel_binding parameters (psycopg-specific)
        # asyncpg handles SSL automatically based on server requirements
        if "?" in url:
            base_url, params = url.split("?", 1)
            # Filter out psycopg-specific params
            filtered_params = [
                p for p in params.split("&")
                if not p.startswith("sslmode=") and not p.startswith("channel_binding=")
            ]
            if filtered_params:
                url = f"{base_url}?{'&'.join(filtered_params)}"
            else:
                url = base_url

        # Ensure +asyncpg driver is specified
        if "postgresql://" in url and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")

        return url


# Global settings instance (singleton pattern)
# Import this in other modules: from .config import settings
settings = Settings()
