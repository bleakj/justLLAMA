"""Tests for Voice Input components: AudioRecorder and VoiceInputManager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from PySide6.QtMultimedia import QMediaRecorder

from justllama.config.settings import AppSettings
from justllama.voice.recorder import AudioRecorder
from justllama.voice.manager import VoiceInputManager


@pytest.fixture()
def settings(qapp, tmp_path, monkeypatch):
    """Return an AppSettings instance backed by a temporary file."""
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
    
    # Force default values
    inst = AppSettings()
    inst.set_bool("chat/voice_input_enabled", True)
    inst.set_string("chat/voice_model", "tiny.en")
    inst.set_bool("chat/voice_send_automatically", False)
    return inst


def test_audio_recorder_init(qapp):
    """Test AudioRecorder initialization and properties."""
    recorder = AudioRecorder()
    assert recorder._recorder is not None
    assert recorder._audio_input is not None
    assert isinstance(recorder._output_path, Path)
    assert not recorder.is_recording()


def test_audio_recorder_start_stop(qapp, monkeypatch):
    """Test start and stop of AudioRecorder with mock QMediaRecorder."""
    recorder = AudioRecorder()
    
    # Mock underlying recorder methods
    mock_record = MagicMock()
    mock_stop = MagicMock()
    state = [QMediaRecorder.RecorderState.StoppedState]
    monkeypatch.setattr(recorder._recorder, "record", mock_record)
    monkeypatch.setattr(recorder._recorder, "stop", mock_stop)
    monkeypatch.setattr(recorder._recorder, "recorderState", lambda: state[0])
    
    recorder.start_recording()
    mock_record.assert_called_once()
    
    state[0] = QMediaRecorder.RecorderState.RecordingState
    recorder.stop_recording()
    mock_stop.assert_called_once()


def test_audio_recorder_on_stopped_success(qapp):
    """Test state change to StoppedState with non-empty output file."""
    recorder = AudioRecorder()
    
    # Write a mock non-empty file to the output path
    recorder._output_path.write_bytes(b"RIFF-WAVE-MOCK-DATA")
    
    # Spy on finished signal using a list collector
    finished_signals = []
    recorder.recording_finished.connect(finished_signals.append)
    
    # Simulate state transition to StoppedState
    recorder._on_state_changed(QMediaRecorder.RecorderState.StoppedState)
    
    assert len(finished_signals) == 1
    assert finished_signals[0] == str(recorder._output_path)
    
    # Clean up
    if recorder._output_path.exists():
        recorder._output_path.unlink()


def test_audio_recorder_on_stopped_failure(qapp):
    """Test state change to StoppedState with empty output file."""
    recorder = AudioRecorder()
    
    # Ensure file is missing or empty
    if recorder._output_path.exists():
        recorder._output_path.unlink()
        
    error_signals = []
    recorder.error_occurred.connect(error_signals.append)
    
    recorder._on_state_changed(QMediaRecorder.RecorderState.StoppedState)
    
    assert len(error_signals) == 1


def test_voice_input_manager_toggle_settings(qapp, settings):
    """Test VoiceInputManager updates when settings are toggled."""
    manager = VoiceInputManager(settings)
    
    assert manager.enabled
    
    # Disable voice input
    settings.set_bool("chat/voice_input_enabled", False)
    # Process events to let settings_changed signal propagate
    qapp.processEvents()
    
    assert not manager.enabled


def test_voice_input_manager_recording_flow(qapp, settings, monkeypatch):
    """Test the recording start/stop flow inside the manager."""
    manager = VoiceInputManager(settings)
    
    mock_start = MagicMock()
    mock_stop = MagicMock()
    monkeypatch.setattr(manager.recorder, "start_recording", mock_start)
    monkeypatch.setattr(manager.recorder, "stop_recording", mock_stop)
    monkeypatch.setattr(manager.recorder, "is_recording", lambda: False)
    
    # Connect signals
    rec_changed = []
    manager.recording_changed.connect(rec_changed.append)
    
    manager.start_recording()
    mock_start.assert_called_once()
    assert rec_changed == [True]
    
    # Mock that it is now recording
    monkeypatch.setattr(manager.recorder, "is_recording", lambda: True)
    rec_changed.clear()
    
    manager.stop_recording()
    mock_stop.assert_called_once()
    assert rec_changed == [False]


def test_voice_input_manager_transcription_success(qapp, settings, monkeypatch):
    """Test successful transcription using a mock Model."""
    manager = VoiceInputManager(settings)
    
    # Mock ASR model and transcribe method
    class MockModel:
        def __init__(self, model_name, *args, **kwargs):
            self.model_name = model_name
        def transcribe(self, wav_path):
            mock_segment = MagicMock()
            mock_segment.text = "Hello from Whisper"
            return [mock_segment]
            
    from pywhispercpp import model as model_mod
    monkeypatch.setattr(model_mod, "Model", MockModel)
    
    # Create the temporary file so validation passes
    temp_wav = Path(manager.recorder._output_path)
    temp_wav.write_bytes(b"RIFF-WAVE-MOCK-DATA")
    
    # Connect signals
    trans_complete = []
    manager.transcription_complete.connect(trans_complete.append)
    
    # Trigger completion of recording which starts worker
    manager._on_recording_finished(str(temp_wav))
    
    # Wait for the background thread to finish
    assert manager._worker is not None
    manager._worker.wait()
    qapp.processEvents()
    
    # Assertions
    assert trans_complete == ["Hello from Whisper"]
    assert not manager.transcribing
    assert not temp_wav.exists()  # check temp file cleaned up
    assert manager._model_instance is not None  # model cached
