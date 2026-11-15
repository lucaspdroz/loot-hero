
import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _int_list(name: str) -> list[int]:
    value = os.getenv(name, "")

    return [
        int(item.strip())
        for item in value.split(",")
        if item.strip().isdigit()
    ]


@dataclass(frozen=True)
class Settings:

    # ==========================================
    # DATABASE
    # ==========================================

    db_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    db_name: str = os.getenv("MYSQL_DATABASE", "games_deals")
    db_user: str = os.getenv("MYSQL_USER", "games_crawler")
    db_password: str = os.getenv("MYSQL_PASSWORD", "")

    # ==========================================
    # EPIC GAMES
    # ==========================================

    epic_enabled: bool = _bool("EPIC_GAMES_ENABLED", True)
    epic_locale: str = os.getenv("EPIC_GAMES_LOCALE", "pt-BR")
    epic_country: str = os.getenv("EPIC_GAMES_COUNTRY", "BR")

    # ==========================================
    # STEAM
    # ==========================================

    steam_enabled: bool = _bool("STEAM_ENABLED", True)

    steam_app_ids: list[int] = None

    steam_country: str = os.getenv("STEAM_COUNTRY", "BR")
    steam_currency: str = os.getenv("STEAM_CURRENCY", "brl")
    steam_language: str = os.getenv(
        "STEAM_LANGUAGE",
        "brazilian",
    )

    steam_page_size: int = int(
        os.getenv("STEAM_PAGE_SIZE", "25")
    )

    steam_max_pages: int = int(
        os.getenv("STEAM_MAX_PAGES", "100")
    )

    steam_request_delay: float = float(
        os.getenv("STEAM_REQUEST_DELAY", "5")
    )

    steam_rate_limit_backoff: float = float(
        os.getenv("STEAM_RATE_LIMIT_BACKOFF", "15")
    )

    # ==========================================
    # HTTP GLOBAL
    # ==========================================

    request_timeout: int = int(
        os.getenv("REQUEST_TIMEOUT", "30")
    )

    request_retries: int = int(
        os.getenv("REQUEST_RETRIES", "3")
    )

    request_delay: float = float(
        os.getenv("REQUEST_DELAY", "5")
    )

    # ==========================================
    # CRAWLER
    # ==========================================

    crawler_interval: int = int(
        os.getenv("CRAWLER_INTERVAL", "21600")
    )

    log_level: str = os.getenv(
        "LOG_LEVEL",
        "INFO",
    ).upper()

    def __post_init__(self):
        if self.steam_app_ids is None:
            object.__setattr__(
                self,
                "steam_app_ids",
                _int_list("STEAM_APP_IDS"),
            )


settings = Settings()
