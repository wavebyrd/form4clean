from __future__ import annotations

import json
from pathlib import Path

import pytest

from form4clean.config import ConfigError, Settings, load_settings, save_settings


def test_missing_email_gives_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="form4clean config --email"):
        Settings(home=tmp_path).user_agent()


def test_invalid_email_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a valid email"):
        load_settings(tmp_path, contact_email="not-an-email")


def test_save_and_load_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("FORM4CLEAN_SEC_EMAIL", "FORM4CLEAN_PRICE_PROVIDER", "FORM4CLEAN_TIINGO_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    settings = load_settings(tmp_path, contact_email="me@example.com", price_provider="csv")
    path = save_settings(settings)
    assert json.loads(path.read_text("utf-8"))["contact_email"] == "me@example.com"
    again = load_settings(tmp_path)
    assert again.user_agent() == "Form4Clean me@example.com"
    assert again.price_provider == "csv"


def test_environment_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    save_settings(load_settings(tmp_path, contact_email="file@example.com"))
    monkeypatch.setenv("FORM4CLEAN_SEC_EMAIL", "env@example.com")
    assert load_settings(tmp_path).contact_email == "env@example.com"


def test_corrupt_config_file(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_settings(tmp_path)
