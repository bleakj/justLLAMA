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
    monkeypatch.setattr(env_module, "_LEGACY_ENV_PATH", missing)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    # Should not raise
    env_module.load_env()
    assert env_module.get_api_key("nvidia") == ""


def test_load_env_prefers_root_but_reads_legacy(tmp_path, monkeypatch):
    """Project-root .env is canonical; legacy in-package .env still loads."""
    root_env = tmp_path / ".env"
    legacy_env = tmp_path / "pkg" / ".env"
    legacy_env.parent.mkdir()
    root_env.write_text("NVIDIA_API_KEY=root-key\n")
    legacy_env.write_text("NVIDIA_API_KEY=legacy-key\nOPENCODE_API_KEY=legacy-only\n")

    monkeypatch.setattr(env_module, "_ENV_PATH", root_env)
    monkeypatch.setattr(env_module, "_LEGACY_ENV_PATH", legacy_env)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    env_module.load_env()
    # Root wins on conflict; legacy fills in what root lacks.
    assert env_module.get_api_key("nvidia") == "root-key"
    assert env_module.get_api_key("opencode") == "legacy-only"
