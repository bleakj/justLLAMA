"""Text-to-speech manager and synthesis worker (WS4).

Kokoro-based, offline TTS. Disabled by default; the user opts in per session
via a chat toggle. The heavy dependency (``kokoro-onnx`` + ``onnxruntime``) is
an optional extra: it is imported lazily so a core install without the ``[tts]``
extra simply reports a friendly message instead of crashing.

Synthesis runs on a background QThread (never the UI thread); playback uses the
already-available Qt Multimedia stack via a temporary WAV file.
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, Property, QThread

logger = logging.getLogger(__name__)

# Conventional model locations; overridable via environment for advanced users.
_TTS_DIR = Path.home() / ".local" / "share" / "justllama" / "tts"
_MODEL_ENV = "KOKORO_MODEL_PATH"
_VOICES_ENV = "KOKORO_VOICES_PATH"


def _model_paths() -> tuple[str, str]:
    """Return (model_path, voices_path) for Kokoro, honoring env overrides."""
    model = os.environ.get(_MODEL_ENV) or str(_TTS_DIR / "kokoro-v0_19.onnx")
    voices = os.environ.get(_VOICES_ENV) or str(_TTS_DIR / "voices.bin")
    return model, voices


class TTSWorker(QThread):
    """Background worker that loads Kokoro and synthesizes speech to a WAV."""

    # Named distinctly so it does NOT shadow QThread's built-in no-arg
    # ``finished`` signal (which stays intact for lifecycle management).
    synthesis_finished = Signal(str, object)  # (wav_path, loaded_model_instance)
    error = Signal(str)

    def __init__(self, text: str, voice: str, cached_model=None, parent=None):
        super().__init__(parent)
        self._text = text
        self._voice = voice
        self._cached_model = cached_model
        self._req_id = 0  # set by the manager to detect superseded results

    def run(self):
        try:
            model = self._cached_model or self._load_model()
            wav_path = self._synthesize(model, self._text, self._voice)
            self.synthesis_finished.emit(wav_path, model)
        except ImportError:
            self.error.emit(
                "Text-to-speech is not installed. Install it with: "
                "pip install 'justllama[tts]'"
            )
        except FileNotFoundError as e:
            self.error.emit(str(e))
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"TTS synthesis failed: {e}", exc_info=True)
            self.error.emit(str(e))

    def _load_model(self):
        """Lazily construct the Kokoro model (raises ImportError if missing)."""
        from kokoro_onnx import Kokoro  # optional [tts] extra

        model_path, voices_path = _model_paths()
        for p in (model_path, voices_path):
            if not Path(p).exists():
                raise FileNotFoundError(
                    f"Kokoro model file not found: {p}. Place the Kokoro ONNX "
                    f"model and voices file under {_TTS_DIR} (or set "
                    f"{_MODEL_ENV}/{_VOICES_ENV})."
                )
        logger.info("TTS: loading Kokoro model on background thread...")
        return Kokoro(model_path, voices_path)

    def _synthesize(self, model, text: str, voice: str) -> str:
        """Synthesize ``text`` and write a 16-bit PCM WAV; return its path."""
        samples, sample_rate = model.create(text, voice=voice, speed=1.0, lang="en-us")
        # Convert float samples in [-1, 1] to little-endian int16 PCM. Use
        # NumPy when available (Kokoro pulls it in) for a fast vectorized path,
        # falling back to a pure-Python loop otherwise.
        try:
            import numpy as np
            arr = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
            pcm = (arr * 32767.0).astype("<i2").tobytes()
        except Exception:
            pcm = bytearray()
            for s in samples:
                v = int(max(-1.0, min(1.0, float(s))) * 32767)
                pcm += int(v).to_bytes(2, "little", signed=True)
            pcm = bytes(pcm)

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="justllama_tts_")
        os.close(fd)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm)
        return wav_path


class TTSManager(QObject):
    """Orchestrates Kokoro synthesis and playback of assistant messages."""

    speaking_changed = Signal(bool)
    enabled_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._model_instance = None
        self._worker = None
        self._active_id = 0  # bumped on each speak()/stop() to supersede results
        self._is_speaking = False
        self._player = None
        self._audio_output = None
        self._current_wav = None
        self._settings.settings_changed.connect(self._on_setting_changed)

    # --- QML Properties ---

    @Property(bool, notify=speaking_changed)
    def speaking(self) -> bool:
        return self._is_speaking

    @Property(bool, notify=enabled_changed)
    def enabled(self) -> bool:
        return self._settings.tts_enabled

    # --- QML Slots / Actions ---

    @Slot(str)
    def speak(self, text: str):
        """Synthesize and play ``text`` if TTS is enabled."""
        if not self.enabled:
            return
        text = (text or "").strip()
        if not text:
            return
        # Only one utterance at a time; a new request replaces the old.
        self.stop()

        self._is_speaking = True
        self.speaking_changed.emit(True)

        self._active_id += 1
        voice = self._settings.tts_voice or "af_sky"
        worker = TTSWorker(text, voice, cached_model=self._model_instance, parent=self)
        worker._req_id = self._active_id
        worker.synthesis_finished.connect(self._on_synth_finished)
        worker.error.connect(self._on_synth_error)
        # Release the worker (and its model reference) once it finishes so dead
        # workers don't accumulate and pin the Kokoro model in memory.
        worker.synthesis_finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    @Slot()
    def stop(self):
        """Stop any current playback and supersede any in-flight synthesis."""
        # Bumping the id makes any pending worker result be discarded.
        self._active_id += 1
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        self._cleanup_temp()
        if self._is_speaking:
            self._is_speaking = False
            self.speaking_changed.emit(False)

    @Slot()
    def unload_model(self):
        """Release the cached Kokoro model to free memory."""
        self.stop()
        # Join any still-running synthesis so we never destroy a live QThread
        # (e.g. when quitting mid-synthesis).
        worker = self._worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.wait(3000)
            except Exception:
                pass
        self._worker = None
        if self._model_instance is not None:
            logger.info("TTS: unloading Kokoro model from memory.")
            self._model_instance = None

    # --- Private helpers ---

    def _on_synth_finished(self, wav_path: str, model):
        # Discard results from a superseded request (a newer speak()/stop()
        # invalidated this one); clean up its temp file.
        worker = self.sender()
        if worker is not None and getattr(worker, "_req_id", None) != self._active_id:
            try:
                p = Path(wav_path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            return
        self._model_instance = model
        self._current_wav = wav_path
        try:
            self._play(wav_path)
        except Exception as e:
            self._is_speaking = False
            self.speaking_changed.emit(False)
            self.error_occurred.emit(f"TTS playback error: {e}")

    def _on_synth_error(self, error_msg: str):
        self._is_speaking = False
        self.speaking_changed.emit(False)
        self.error_occurred.emit(f"TTS error: {error_msg}")

    def _play(self, wav_path: str):
        """Play a WAV file via Qt Multimedia (non-blocking)."""
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtCore import QUrl

        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.setSource(QUrl.fromLocalFile(wav_path))
        self._player.play()

    def _on_playback_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._cleanup_temp()
            if self._is_speaking:
                self._is_speaking = False
                self.speaking_changed.emit(False)

    def _cleanup_temp(self):
        if self._current_wav:
            try:
                p = Path(self._current_wav)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            self._current_wav = None

    def _on_setting_changed(self, key: str, value):
        if key == "chat/tts_enabled":
            self.enabled_changed.emit(self.enabled)
            if not self.enabled:
                self.unload_model()
