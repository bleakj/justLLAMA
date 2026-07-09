"""Tests for the .env-backed secret API key module."""

import pytest

import justllama.config.env as env_module


def test_get_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "x")
    assert env_module.get_api_key("nvidia") == "x"
    # Unset provider returns empty string
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert env_module.get_api_key("openrouter") == ""


def test_get_api_key_unknown_provider_raises(monkeypatch):
    with pytest.raises(ValueError):
        env_module.get_api_key("bogus")


def test_set_api_key_writes_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env_module, "_ENV_PATH", env_file)
    # Start from a clean environment for the provider
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    env_module.set_api_key("openrouter", "sk-123")

    # python-dotenv may single-quote values with special chars; assert the
    # key line is present and the value is retrievable unquoted.
    assert "OPENROUTER_API_KEY=" in env_file.read_text()
    assert env_module.get_api_key("openrouter") == "sk-123"


def test_load_env_missing_file_no_error(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist" / ".env"
    monkeypatch.setattr(env_module, "_ENV_PATH", missing)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    # Should not raise
    env_module.load_env()
    assert env_module.get_api_key("nvidia") == ""
