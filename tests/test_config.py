import pytest
from pydantic import ValidationError

from fitosanitarios.config import Settings


def test_settings_requiere_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_defaults_con_fixtures(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    settings = Settings(_env_file=None)
    assert settings.use_fixtures is True
    assert settings.llm_provider == "gemini"
    assert settings.gemini_api_keys == []


def test_settings_falla_sin_api_key_si_no_usa_fixtures(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("USE_FIXTURES", "false")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY_1", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_ok_con_api_key_y_sin_fixtures(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("USE_FIXTURES", "false")
    monkeypatch.setenv("GEMINI_API_KEY_1", "abc")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_keys == ["abc"]


def test_settings_falla_groq_sin_api_key_si_no_usa_fixtures(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("USE_FIXTURES", "false")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
