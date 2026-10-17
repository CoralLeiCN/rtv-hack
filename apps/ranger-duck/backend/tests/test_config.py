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


def test_explicit_env_file_shared_by_settings_and_exporter(env_file, tmp_path, monkeypatch):
    shared = tmp_path / 'shared.env'
    shared.write_text('INGRESS_URL=https://shared.invalid\nUSERNAME=shared-user\n'
                      'PASSWORD=shared-password\nWANDB_API_KEY=test-key\nRANGER_WEAVE_PROJECT=team/project\n')
    env_file.write_text('WANDB_API_KEY=wrong-file-key\n')
    monkeypatch.setenv('RANGER_ENV_FILE', str(shared))
    monkeypatch.chdir(tmp_path.parent)
    assert config.env_file() == shared
    assert config.env_values()['WANDB_API_KEY'] == 'test-key'
    assert config.Settings.from_env().username == 'shared-user'
    # Changing configuration location must not combine different worktrees' captures.
    assert config.Settings.from_env().capture_dir == env_file.parent / '.captures'


@pytest.mark.parametrize('path', ['relative.env', '/missing/ranger.env'])
def test_explicit_env_file_does_not_silently_fall_back(env_file, monkeypatch, path):
    monkeypatch.setenv('RANGER_ENV_FILE', path)
    with pytest.raises(ValueError, match='existing absolute file path'):
        config.env_values()
