"""Application configuration."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Steam API
    steam_api_key: str
    steam_partner_key: str | None = None

    # Database
    database_url: str
    database_url_sync: str | None = None

    # API Security
    api_secret_key: str

    # Publisher Configuration
    publisher_id: str = "FirstBreakLabs"
    publisher_games: str = ""  # Comma-separated app IDs

    # Collection Settings
    collection_interval_hours: int = 6
    market_collection_interval_hours: int = 24
    revenue_collection_interval_hours: int = 24

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    @property
    def portfolio_app_ids(self) -> list[int]:
        """Parse publisher_games into list of app IDs."""
        if not self.publisher_games:
            return []
        return [int(x.strip()) for x in self.publisher_games.split(",") if x.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
