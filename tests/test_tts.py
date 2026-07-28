"""Tests for the TTS manager (WS4) — settings gating, worker logic, no audio.

These tests never invoke real Kokoro synthesis or audio playback; they mock the
worker and verify the manager's settings-gated enable/disable/unload behavior.
"""

import importlib.util

import pytest
from unittest.mock import MagicMock

from justllama.config.settings import AppSettings
from justllama.voice.tts_manager import TTSManager, TTSWorker


@pytest.fixture()
def settings(qapp, tmp_path, monkeypatch):
    """AppSettings backed by a temporary INI file."""
    settings_file = str(tmp_path / "test_settings.conf")
    from justllama.config import settings as settings_mod

    class _TestQSettings:
        def __init__(self, *args, **kwargs):
            from PySide6.QtCore import QSettings
            self._qs = QSettings(settings_file, QSettings.IniFormat)

        def value(self, key, default=None):
            return self._qs.value(key, default)

        def setValue(self, key, value):
            self._qs.setValue(key, value)

        def sync(self):
            self._qs.sync()

    monkeypatch.setattr(settings_mod, "QSettings", _TestQSettings)
    return AppSettings()


def test_disabled_by_default(settings):
    mgr = TTSManager(settings)
    assert mgr.enabled is False


def test_speak_noop_when_disabled(settings):
    mgr = TTSManager(settings)
    settings.set_bool("chat/tts_enabled", False)
    # No worker should be created when disabled.
    mgr.speak("hello world")
    assert mgr._worker is None
    assert mgr.speaking is False


def test_speak_starts_worker_when_enabled(settings, monkeypatch):
    mgr = TTSManager(settings)
    settings.set_bool("chat/tts_enabled", True)

    started = {}

    class _FakeWorker:
        finished = MagicMock()
        error = MagicMock()

        def __init__(self, text, voice, cached_model=None, parent=None):
            started["text"] = text
            started["voice"] = voice
            self.synthesis_finished = MagicMock()
            self.error = MagicMock()
            self.deleteLater = MagicMock()
            self._req_id = 0

        def start(self):
            started["started"] = True

    monkeypatch.setattr("justllama.voice.tts_manager.TTSWorker", _FakeWorker)
    mgr.speak("read this")
    assert started.get("started") is True
    assert started["text"] == "read this"
    assert mgr.speaking is True


def test_speak_ignores_empty_text(settings):
    mgr = TTSManager(settings)
    settings.set_bool("chat/tts_enabled", True)
    mgr.speak("   ")
    assert mgr._worker is None


def test_disabling_setting_unloads_model(settings):
    mgr = TTSManager(settings)
    settings.set_bool("chat/tts_enabled", True)
    mgr._model_instance = object()  # pretend a model is loaded
    settings.set_bool("chat/tts_enabled", False)  # emits settings_changed
    assert mgr._model_instance is None


def test_unload_model_clears_instance(settings):
    mgr = TTSManager(settings)
    mgr._model_instance = object()
    mgr.unload_model()
    assert mgr._model_instance is None


def test_worker_reports_missing_extra(qapp, monkeypatch):
    """If kokoro_onnx is not importable, the worker emits a friendly error."""
    if importlib.util.find_spec("kokoro_onnx") is not None:
        pytest.skip("kokoro_onnx is installed; import-error path not exercised")

    worker = TTSWorker("hi", "af_sky")
    errors = []
    worker.error.connect(errors.append)
    worker.run()  # synchronous
    assert len(errors) == 1
    assert "pip install" in errors[0]


def test_synthesize_writes_wav(qapp, tmp_path):
    """_synthesize converts samples to a valid 16-bit PCM WAV file."""
    import wave

    worker = TTSWorker("hi", "af_sky")
    fake_model = MagicMock()
    fake_model.create.return_value = ([0.0, 0.5, -0.5, 1.0, -1.0], 24000)

    path = worker._synthesize(fake_model, "hi", "af_sky")
    try:
        with wave.open(path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 24000
            assert wf.getnframes() == 5
    finally:
        import os
        os.unlink(path)
