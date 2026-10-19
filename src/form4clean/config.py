"""Settings: where data lives, how Form4Clean identifies itself to the SEC, and price providers.

Settings are read from, in order of precedence:

1. Environment variables (``FORM4CLEAN_*``).
2. ``config.json`` in the data directory, written by ``form4clean config``.
3. Defaults.

The SEC asks automated clients to send a User-Agent that names the application and gives a
contact email (https://www.sec.gov/os/accessing-edgar-data). Form4Clean refuses to contact the
SEC until one is configured, rather than inventing one.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

DEFAULT_APP_NAME = "Form4Clean"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# The SEC's published fair-access limit is 10 requests per second. Stay well under it.
DEFAULT_REQUESTS_PER_SECOND = 5.0
MAX_REQUESTS_PER_SECOND = 10.0


class ConfigError(Exception):
    """Raised when configuration is missing or invalid. The message says how to fix it."""


def default_home() -> Path:
    env = os.environ.get("FORM4CLEAN_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".form4clean"


class Settings(BaseModel):
    home: Path = Field(default_factory=default_home)
    contact_email: str | None = None
    app_name: str = DEFAULT_APP_NAME
    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND
    max_retries: int = 5
    timeout_seconds: float = 30.0
    submissions_ttl_hours: float = 6.0
    price_provider: str = "none"
    csv_price_dir: Path | None = None

    @field_validator("contact_email")
    @classmethod
    def _check_email(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if not EMAIL_RE.fullmatch(value):
            raise ValueError(f"{value!r} is not a valid email address")
        return value

    @field_validator("requests_per_second")
    @classmethod
    def _check_rate(cls, value: float) -> float:
        if not 0 < value <= MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                f"requests_per_second must be between 0 and {MAX_REQUESTS_PER_SECOND} "
                "(the SEC fair-access limit)"
            )
        return value

    @property
    def db_path(self) -> Path:
        return self.home / "form4clean.duckdb"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def config_path(self) -> Path:
        return self.home / "config.json"

    @property
    def prices_dir(self) -> Path:
        return self.csv_price_dir or (self.home / "prices")

    def user_agent(self) -> str:
        """The User-Agent sent to the SEC. Raises ConfigError if no contact email is set."""
        if not self.contact_email:
            raise ConfigError(
                "The SEC requires a contact email in the User-Agent of automated requests.\n"
                'Set one with:  form4clean config --email "you@example.com"\n'
                "or the FORM4CLEAN_SEC_EMAIL environment variable."
            )
        return f"{self.app_name} {self.contact_email}"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


_ENV_MAP: dict[str, str] = {
    "FORM4CLEAN_SEC_EMAIL": "contact_email",
    "FORM4CLEAN_SEC_APP_NAME": "app_name",
    "FORM4CLEAN_REQUESTS_PER_SECOND": "requests_per_second",
    "FORM4CLEAN_PRICE_PROVIDER": "price_provider",
    "FORM4CLEAN_CSV_PRICE_DIR": "csv_price_dir",
}

# Fields that may be saved to config.json.
PERSISTED_FIELDS = (
    "contact_email",
    "app_name",
    "requests_per_second",
    "price_provider",
    "csv_price_dir",
)


def load_settings(home: Path | None = None, **overrides: Any) -> Settings:
    """Build settings from the config file, environment, and explicit overrides."""
    base_home = home or default_home()
    values: dict[str, Any] = {"home": base_home}
    config_path = base_home / "config.json"
    if config_path.exists():
        try:
            saved = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{config_path} is not valid JSON: {exc}. Fix or delete it.") from exc
        values.update({k: v for k, v in saved.items() if k in PERSISTED_FIELDS})
    for env, field in _ENV_MAP.items():
        if os.environ.get(env):
            values[field] = os.environ[env]
    values.update({k: v for k, v in overrides.items() if v is not None})
    try:
        return Settings(**values)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def save_settings(settings: Settings) -> Path:
    """Write the persistable settings to config.json and return its path."""
    settings.ensure_dirs()
    data = settings.model_dump(mode="json", include=set(PERSISTED_FIELDS))
    settings.config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return settings.config_path
