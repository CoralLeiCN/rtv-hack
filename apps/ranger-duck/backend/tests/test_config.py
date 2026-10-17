import os

import pytest

from ranger_duck import config


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name in {"ARCHIVE_URL", "EXAMPLE_NAME", "ARCHIVE_API_KEY"} or name.startswith("RANGER_"):
            monkeypatch.delenv(name)
    path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", path)
    return path


def test_dotenv_loads_from_backend_path_with_literal_key(env_file, monkeypatch, tmp_path):
    env_file.write_text('ARCHIVE_URL=https://archive.invalid/\nEXAMPLE_NAME=test-secret\n'
                        'ARCHIVE_API_KEY=\'literal-${EXAMPLE_NAME}-key\'\n'
                        'RANGER_SEARCH_TIMEOUT_SEC=45\n')
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    settings = config.Settings.from_env()
    assert settings.configured
    assert settings.archive_url == "https://archive.invalid"
    assert settings.api_key == "literal-${EXAMPLE_NAME}-key"
    assert settings.search_timeout_sec == 45
    assert "ARCHIVE_API_KEY" not in os.environ


def test_exported_values_override_dotenv_including_empty_values(env_file, monkeypatch):
    env_file.write_text('ARCHIVE_URL=https://archive.invalid\nEXAMPLE_NAME=file-user\nARCHIVE_API_KEY=file-password\n')
    monkeypatch.setenv("EXAMPLE_NAME", "exported-user")
    monkeypatch.setenv("ARCHIVE_API_KEY", "")
    settings = config.Settings.from_env()
    assert settings.api_key == ""
    assert not settings.configured


def test_missing_dotenv_keeps_no_config_startup(env_file):
    settings = config.Settings.from_env()
    assert not settings.configured
    assert settings.search_timeout_sec == 30


def test_explicit_env_file_shared_by_settings_and_exporter(env_file, tmp_path, monkeypatch):
    shared = tmp_path / 'shared.env'
    shared.write_text('ARCHIVE_URL=https://shared.invalid\nEXAMPLE_NAME=shared-user\n'
                      'ARCHIVE_API_KEY=shared-password\nWANDB_API_KEY=test-key\nRANGER_WEAVE_PROJECT=team/project\n')
    env_file.write_text('WANDB_API_KEY=wrong-file-key\n')
    monkeypatch.setenv('RANGER_ENV_FILE', str(shared))
    monkeypatch.chdir(tmp_path.parent)
    assert config.env_file() == shared
    assert config.env_values()['WANDB_API_KEY'] == 'test-key'
    assert config.Settings.from_env().api_key == 'shared-password'
    # Changing configuration location must not combine different worktrees' captures.
    assert config.Settings.from_env().capture_dir == env_file.parent / '.captures'


@pytest.mark.parametrize('path', ['relative.env', '/missing/ranger.env'])
def test_explicit_env_file_does_not_silently_fall_back(env_file, monkeypatch, path):
    monkeypatch.setenv('RANGER_ENV_FILE', path)
    with pytest.raises(ValueError, match='existing absolute file path'):
        config.env_values()
