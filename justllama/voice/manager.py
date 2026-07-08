"""Voice input manager and ASR transcription worker."""

import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, Property, QThread

from justllama.voice.recorder import AudioRecorder

logger = logging.getLogger(__name__)


class ASRWorker(QThread):
    """Background worker to load the model and run ASR transcription."""

    finished = Signal(str, object)  # Emitted with (transcribed_text, loaded_model_instance)
    error = Signal(str)             # Emitted with error message

    def __init__(self, wav_path: str, model_name: str, cached_model=None, parent=None):
        super().__init__(parent)
        self._wav_path = wav_path
        self._model_name = model_name
        self._cached_model = cached_model

    def run(self):
        try:
            # Lazy import pywhispercpp to avoid application startup overhead
            from pywhispercpp.model import Model

            model = self._cached_model
            # If no cached model, or if the model name changed, load/reload
            if model is None:
                logger.info(f"Voice Input: Loading ASR model '{self._model_name}' on background thread...")
                model = Model(self._model_name)
            else:
                logger.debug("Voice Input: Using cached ASR model.")

            # Perform transcription
            logger.info(f"Voice Input: Transcribing {self._wav_path}...")
            segments = model.transcribe(self._wav_path)
            
            # Join transcription segments
            transcribed_text = "".join(seg.text for seg in segments).strip()
            logger.info(f"Voice Input: Transcription finished: '{transcribed_text}'")

            self.finished.emit(transcribed_text, model)

        except Exception as e:
            logger.error(f"Voice Input: Transcription failed: {e}", exc_info=True)
            self.error.emit(str(e))


class VoiceInputManager(QObject):
    """Orchestrates microphone recording and Whisper transcription."""

    # QML Signals
    recording_changed = Signal(bool)
    transcribing_changed = Signal(bool)
    enabled_changed = Signal(bool)
    transcription_complete = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._recorder = None
        self._model_instance = None
        self._model_name_cached = None
        self._is_transcribing = False
        self._worker = None
        # Connect setting change signal to react to toggle/unload
        self._settings.settings_changed.connect(self._on_setting_changed)

    @property
    def recorder(self) -> AudioRecorder:
        """Lazy-loaded AudioRecorder instance."""
        if self._recorder is None:
            self._recorder = AudioRecorder(parent=self)
            self._recorder.recording_finished.connect(self._on_recording_finished)
            self._recorder.error_occurred.connect(self._on_recorder_error)
        return self._recorder

    # --- QML Properties ---

    @Property(bool, notify=recording_changed)
    def recording(self) -> bool:
        """True if recording audio from microphone."""
        if self._recorder is None:
            return False
        return self._recorder.is_recording()

    @Property(bool, notify=transcribing_changed)
    def transcribing(self) -> bool:
        """True if transcribing audio."""
        return self._is_transcribing

    @Property(bool, notify=enabled_changed)
    def enabled(self) -> bool:
        """True if Voice Input is enabled in settings."""
        return self._settings.voice_input_enabled

    # --- QML Slots / Actions ---

    @Slot()
    def start_recording(self):
        """Start microphone recording."""
        if not self.enabled:
            logger.warning("Voice Input: Cannot start recording when voice input is disabled.")
            return
        
        if self._is_transcribing:
            logger.warning("Voice Input: Cannot record while transcription is in progress.")
            return

        self.recorder.start_recording()
        self.recording_changed.emit(True)

    @Slot()
    def stop_recording(self):
        """Stop microphone recording and trigger transcription."""
        if not self.recording:
            logger.debug("Voice Input: Not recording, ignoring stop.")
            return

        self.recorder.stop_recording()
        self.recording_changed.emit(False)

    @Slot()
    def unload_model(self):
        """Unload the Whisper model to free memory."""
        if self._model_instance is not None:
            logger.info("Voice Input: Unloading Whisper model from memory.")
            self._model_instance = None
            self._model_name_cached = None

    # --- Private Helpers ---

    def _on_recording_finished(self, wav_path: str):
        """Trigger background ASR transcription once audio file is saved."""
        model_name = self._settings.voice_model
        
        # If the user changed the model name, discard old cached model
        if self._model_name_cached != model_name:
            self._model_instance = None
            self._model_name_cached = model_name

        self._is_transcribing = True
        self.transcribing_changed.emit(True)

        # Create and start worker
        self._worker = ASRWorker(
            wav_path=wav_path,
            model_name=model_name,
            cached_model=self._model_instance,
            parent=self
        )
        self._worker.finished.connect(self._on_transcription_finished)
        self._worker.error.connect(self._on_transcription_error)
        self._worker.start()

    def _on_transcription_finished(self, text: str, model):
        """Called when ASR thread completes transcription successfully."""
        self._model_instance = model
        self._is_transcribing = False
        self.transcribing_changed.emit(False)

        # Clean up temp file
        try:
            if self._recorder is not None:
                temp_file = Path(self._recorder._output_path)
                if temp_file.exists():
                    temp_file.unlink()
        except Exception as e:
            logger.warning(f"Voice Input: Failed to delete temp wav file: {e}")

        # Emit text to QML
        self.transcription_complete.emit(text)

    def _on_transcription_error(self, error_msg: str):
        """Called when ASR thread fails."""
        self._is_transcribing = False
        self.transcribing_changed.emit(False)
        self.error_occurred.emit(f"Transcription error: {error_msg}")

    def _on_recorder_error(self, error_msg: str):
        """Called when recorder fails."""
        self.recording_changed.emit(False)
        self.error_occurred.emit(f"Recording error: {error_msg}")

    def _on_setting_changed(self, key: str, value):
        """Handle changes in settings, unloading the model if feature is disabled."""
        if key == "chat/voice_input_enabled":
            self.enabled_changed.emit(self.enabled)
            if not self.enabled:
                self.unload_model()
        elif key == "chat/voice_model":
            # If model name changed, unload the old model immediately
            if self._model_name_cached != value:
                self.unload_model()
