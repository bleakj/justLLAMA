"""Tests for justllama.config.settings.AppSettings.

All tests use a temporary QSettings location to avoid polluting the real
user config. A session-scoped QCoreApplication is shared across tests.
"""

import pytest
from PySide6.QtCore import QCoreApplication, QSettings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Provide a single QCoreApplication for the entire test session."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture()
def settings(qapp, tmp_path, monkeypatch):
    """Return an AppSettings instance backed by a temporary INI file.

    Monkeypatches the QSettings constructor so AppSettings never touches
    the real ``~/.config/justllama/`` directory.
    """
    settings_file = str(tmp_path / "test_settings.conf")

    # Intercept QSettings construction inside the settings module so that
    # AppSettings.__init__ creates a file-backed QSettings pointing at our
    # temporary path instead of the real user config.
    original_init = QSettings.__init__

    def _patched_init(self, org_or_path="", app_or_format="", *args, **kwargs):
        # Force a file-based QSettings using our temp path so nothing leaks.
        original_init(self, settings_file, QSettings.IniFormat)

    monkeypatch.setattr(
        "justllama.config.settings.QSettings", lambda *a, **k: None  # placeholder
    )

    # Actually, easier: just patch __init__ on the class used in the module.
    # Simpler approach: import and construct directly with the patch.
    from justllama.config import settings as settings_mod

    original_qs = settings_mod.QSettings

    class _TestQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_file, QSettings.IniFormat)

    monkeypatch.setattr(settings_mod, "QSettings", _TestQSettings)

    from justllama.config.settings import AppSettings
    instance = AppSettings()
    yield instance


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------

class TestTypedAccessors:
    def test_get_string_returns_string(self, settings):
        settings.set_string("test/str", "hello world")
        assert settings.get_string("test/str") == "hello world"

    def test_get_int_returns_int(self, settings):
        settings.set_int("test/int", 42)
        assert settings.get_int("test/int") == 42

    def test_get_bool_returns_bool(self, settings):
        settings.set_bool("test/bool", True)
        assert settings.get_bool("test/bool") is True

    def test_get_bool_false(self, settings):
        settings.set_bool("test/bool_f", False)
        assert settings.get_bool("test/bool_f") is False

    def test_get_string_missing_key_returns_empty(self, settings):
        assert settings.get_string("nonexistent/key") == ""

    def test_get_int_missing_key_returns_zero(self, settings):
        assert settings.get_int("nonexistent/key") == 0

    def test_get_bool_missing_key_returns_false(self, settings):
        assert settings.get_bool("nonexistent/key") is False

    def test_set_string_emits_signal(self, settings):
        received = []
        settings.settings_changed.connect(lambda k, v: received.append((k, v)))
        settings.set_string("test/sig_str", "value")
        assert ("test/sig_str", "value") in received

    def test_set_int_emits_signal(self, settings):
        received = []
        settings.settings_changed.connect(lambda k, v: received.append((k, v)))
        settings.set_int("test/sig_int", 99)
        assert ("test/sig_int", 99) in received

    def test_set_bool_emits_signal(self, settings):
        received = []
        settings.settings_changed.connect(lambda k, v: received.append((k, v)))
        settings.set_bool("test/sig_bool", True)
        assert ("test/sig_bool", True) in received

    def test_set_string_persists(self, settings):
        settings.set_string("test/persist_str", "persisted")
        # Create a fresh getter via the underlying QSettings to confirm storage
        assert settings.get_string("test/persist_str") == "persisted"

    def test_set_int_persists(self, settings):
        settings.set_int("test/persist_int", 123)
        assert settings.get_int("test/persist_int") == 123

    def test_set_bool_persists(self, settings):
        settings.set_bool("test/persist_bool", True)
        assert settings.get_bool("test/persist_bool") is True


# ---------------------------------------------------------------------------
# Convenience properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_server_port_returns_int(self, settings):
        settings.set_int("server/port", 9090)
        assert settings.server_port == 9090
        assert isinstance(settings.server_port, int)

    def test_model_path_returns_string(self, settings):
        settings.set_string("server/model_path", "/tmp/model.gguf")
        assert settings.model_path == "/tmp/model.gguf"

    def test_models_directory_returns_string(self, settings):
        settings.set_string("models/directory", "/tmp/models")
        assert settings.models_directory == "/tmp/models"

    def test_rag_enabled_returns_bool(self, settings):
        settings.set_bool("rag/enabled", True)
        assert settings.rag_enabled is True
        settings.set_bool("rag/enabled", False)
        assert settings.rag_enabled is False

    def test_memory_enabled_returns_bool(self, settings):
        settings.set_bool("memory/enabled", True)
        assert settings.memory_enabled is True
        settings.set_bool("memory/enabled", False)
        assert settings.memory_enabled is False


# ---------------------------------------------------------------------------
# get_all_server_config()
# ---------------------------------------------------------------------------

class TestGetAllServerConfig:
    def test_returns_dict_with_all_keys(self, settings):
        cfg = settings.get_all_server_config()
        expected_keys = {
            "binary", "model_path", "port", "ctx_size",
            "n_gpu_layers", "threads", "batch_size", "ubatch_size",
            "flash_attn", "mmap", "mlock", "numa", "extra_args",
        }
        assert set(cfg.keys()) == expected_keys

    def test_values_match_individual_getters(self, settings):
        settings.set_string("server/binary", "/usr/bin/llama-server")
        settings.set_string("server/model_path", "/data/model.gguf")
        settings.set_int("server/port", 8081)
        settings.set_int("server/ctx_size", 2048)
        settings.set_int("server/n_gpu_layers", 33)
        settings.set_int("server/threads", 4)
        settings.set_int("server/batch_size", 256)
        settings.set_bool("server/flash_attn", False)

        cfg = settings.get_all_server_config()

        assert cfg["binary"] == settings.get_string("server/binary")
        assert cfg["model_path"] == settings.get_string("server/model_path")
        assert cfg["port"] == settings.get_int("server/port")
        assert cfg["ctx_size"] == settings.get_int("server/ctx_size")
        assert cfg["n_gpu_layers"] == settings.get_int("server/n_gpu_layers")
        assert cfg["threads"] == settings.get_int("server/threads")
        assert cfg["batch_size"] == settings.get_int("server/batch_size")
        assert cfg["flash_attn"] == settings.get_bool("server/flash_attn")

    def test_actual_values_in_dict(self, settings):
        settings.set_int("server/port", 8081)
        settings.set_int("server/ctx_size", 2048)
        cfg = settings.get_all_server_config()
        assert cfg["port"] == 8081
        assert cfg["ctx_size"] == 2048


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    @pytest.fixture()
    def fresh_settings(self, qapp, tmp_path, monkeypatch):
        """A brand-new AppSettings with no prior state in a clean temp dir."""
        from justllama.config import settings as settings_mod

        settings_file = str(tmp_path / "fresh_settings.conf")

        class _TestQSettings(QSettings):
            def __init__(self, *args, **kwargs):
                super().__init__(settings_file, QSettings.IniFormat)

        monkeypatch.setattr(settings_mod, "QSettings", _TestQSettings)

        from justllama.config.settings import AppSettings
        return AppSettings()

    def test_default_port(self, fresh_settings):
        assert fresh_settings.get_int("server/port") == 8080

    def test_default_ctx_size(self, fresh_settings):
        assert fresh_settings.get_int("server/ctx_size") == 4096

    def test_default_n_gpu_layers(self, fresh_settings):
        assert fresh_settings.get_int("server/n_gpu_layers") == 99

    def test_default_threads(self, fresh_settings):
        assert fresh_settings.get_int("server/threads") == -1

    def test_default_batch_size(self, fresh_settings):
        assert fresh_settings.get_int("server/batch_size") == 512

    def test_default_flash_attn(self, fresh_settings):
        assert fresh_settings.get_bool("server/flash_attn") is True

    def test_default_model_path_empty(self, fresh_settings):
        assert fresh_settings.get_string("server/model_path") == ""

    def test_default_rag_disabled(self, fresh_settings):
        assert fresh_settings.get_bool("rag/enabled") is False

    def test_default_memory_disabled(self, fresh_settings):
        assert fresh_settings.get_bool("memory/enabled") is False

    def test_default_rag_chunk_size(self, fresh_settings):
        assert fresh_settings.get_int("rag/chunk_size") == 512

    def test_default_rag_chunk_overlap(self, fresh_settings):
        assert fresh_settings.get_int("rag/chunk_overlap") == 50

    def test_default_max_short_term(self, fresh_settings):
        assert fresh_settings.get_int("memory/max_short_term") == 50

    def test_default_chat_mode(self, fresh_settings):
        assert fresh_settings.get_string("chat/mode") == "chat"

    def test_default_council_models(self, fresh_settings):
        assert fresh_settings.get_string("council/model_1") == ""
        assert fresh_settings.get_string("council/model_2") == ""
        assert fresh_settings.get_string("council/model_3") == ""

    def test_server_port_property_uses_default(self, fresh_settings):
        assert fresh_settings.server_port == 8080
        assert isinstance(fresh_settings.server_port, int)

    def test_models_directory_property_has_default(self, fresh_settings):
        val = fresh_settings.models_directory
        assert isinstance(val, str)
        assert "models" in val.lower()

    def test_defaults_not_overwritten_on_second_init(self, qapp, tmp_path, monkeypatch):
        """Creating AppSettings twice with the same backing store should not
        overwrite values that were explicitly set between the two inits."""
        from justllama.config import settings as settings_mod

        settings_file = str(tmp_path / "persist_defaults.conf")

        class _TestQSettings(QSettings):
            def __init__(self, *args, **kwargs):
                super().__init__(settings_file, QSettings.IniFormat)

        monkeypatch.setattr(settings_mod, "QSettings", _TestQSettings)

        from justllama.config.settings import AppSettings

        s1 = AppSettings()
        s1.set_int("server/port", 9999)

        s2 = AppSettings()
        assert s2.get_int("server/port") == 9999
