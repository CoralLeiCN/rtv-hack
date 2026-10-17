import os

import pytest

from ranger_duck import config


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name in {"INGRESS_URL", "USERNAME", "PASSWORD"} or name.startswith("RANGER_"):
            monkeypatch.delenv(name)
    path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", path)
    return path


def test_dotenv_loads_from_backend_path_with_literal_password(env_file, monkeypatch, tmp_path):
    env_file.write_text('INGRESS_URL=https://vss.invalid/\nUSERNAME=test-user\n'
                        'PASSWORD=\'literal ${USERNAME} # password\'\n'
                        'RANGER_SEARCH_TIMEOUT_SEC=45\n')
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    settings = config.Settings.from_env()
    assert settings.configured
    assert settings.ingress_url == "https://vss.invalid"
    assert settings.password == "literal ${USERNAME} # password"
    assert settings.search_timeout_sec == 45
    assert "PASSWORD" not in os.environ


def test_exported_values_override_dotenv_including_empty_values(env_file, monkeypatch):
    env_file.write_text('INGRESS_URL=https://vss.invalid\nUSERNAME=file-user\nPASSWORD=file-password\n')
    monkeypatch.setenv("USERNAME", "exported-user")
    monkeypatch.setenv("PASSWORD", "")
    settings = config.Settings.from_env()
    assert settings.username == "exported-user"
    assert settings.password == ""
    assert not settings.configured


def test_missing_dotenv_keeps_no_config_startup(env_file):
    settings = config.Settings.from_env()
    assert not settings.configured
    assert settings.search_timeout_sec == 30
