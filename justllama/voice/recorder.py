"""Audio recorder backend using PySide6.QtMultimedia."""

import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtMultimedia import QMediaCaptureSession, QAudioInput, QMediaRecorder, QMediaFormat, QMediaDevices

logger = logging.getLogger(__name__)


class AudioRecorder(QObject):
    """Handles local microphone audio capture to a temporary WAV file."""

    recording_finished = Signal(str)  # Emitted with the path to the recorded WAV file
    error_occurred = Signal(str)      # Emitted when an error occurs

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session = QMediaCaptureSession()
        self._audio_input = QAudioInput()
        self._session.setAudioInput(self._audio_input)

        self._recorder = QMediaRecorder()
        self._session.setRecorder(self._recorder)

        # Configure audio format to 16,000 Hz, mono, 16-bit PCM (WAV)
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        self._recorder.setMediaFormat(media_format)

        self._recorder.setAudioChannelCount(1)
        self._recorder.setAudioSampleRate(16000)

        # Connect signals
        self._recorder.errorOccurred.connect(self._on_recorder_error)
        self._recorder.recorderStateChanged.connect(self._on_state_changed)

        # Define default output path
        app_dir = Path.home() / ".local" / "share" / "justllama"
        app_dir.mkdir(parents=True, exist_ok=True)
        self._output_path = app_dir / "temp_voice.wav"

        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self._output_path)))

        # Log status of microphone devices
        devices = QMediaDevices.audioInputs()
        if not devices:
            logger.warning("Voice Input: No audio input devices detected.")

    @Slot()
    def start_recording(self):
        """Start recording audio."""
        if self.is_recording():
            logger.debug("Voice Input: Already recording, ignoring start request.")
            return

        # Ensure any previous file is removed
        if self._output_path.exists():
            try:
                self._output_path.unlink()
            except Exception as e:
                logger.error(f"Voice Input: Failed to delete previous recording: {e}")

        logger.info("Voice Input: Starting audio recording...")
        self._recorder.record()

    @Slot()
    def stop_recording(self):
        """Stop recording audio."""
        if not self.is_recording():
            logger.debug("Voice Input: Not recording, ignoring stop request.")
            return

        logger.info("Voice Input: Stopping audio recording...")
        self._recorder.stop()

    def is_recording(self) -> bool:
        """Check if recording is in progress."""
        return self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState

    def _on_recorder_error(self, error, error_string):
        logger.error(f"Voice Input: Recorder error: {error_string} (code: {error})")
        self.error_occurred.emit(error_string)

    def _on_state_changed(self, state):
        logger.debug(f"Voice Input: Recorder state changed to {state}")
        if state == QMediaRecorder.RecorderState.StoppedState:
            # When stopped, check if the file was successfully written
            if self._output_path.exists() and self._output_path.stat().st_size > 0:
                logger.info(f"Voice Input: Recording saved to {self._output_path}")
                self.recording_finished.emit(str(self._output_path))
            else:
                err_msg = "Voice Input: Recording failed or no audio data captured (0 bytes)."
                logger.warning(err_msg)
                self.error_occurred.emit(err_msg)
