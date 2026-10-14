"""Wake word + VAD adapters.

OpenWakeWordDetector: openWakeWord (fully local, no API key). The model
is loaded once; ``score(frame)`` returns the wake word confidence
(0.0-1.0). The runtime compares it to the configured threshold, so
the detector itself holds no threshold. ONNX is the inference
framework -- tflite-runtime fails on this Pi (SystemError in
CreateWrapperFromFile when loading the model).

SileroVAD: pysilero-vad (Silero VAD v6, bundled ggml model). The 160 ms
frame is split into five 512-sample chunks (Silero chunk size);
speech if any chunk scores >= threshold.
"""

from __future__ import annotations

from .errors import AudioError

WAKE_FRAME_SAMPLES = 2560  # 160 ms at 16 kHz


class OpenWakeWordDetector:
    """Wake word detector backed by openWakeWord."""

    def __init__(
        self,
        model_name: str = "hey_jarvis",
        framework: str = "onnx",
    ) -> None:
        try:
            import numpy as np
            from openwakeword.model import Model
        except ImportError as exc:
            raise AudioError(
                "openwakeword is not installed; cannot use the wake word"
            ) from exc
        self._np = np
        self.model_name = model_name
        try:
            self._model = Model(
                wakeword_models=[model_name], inference_framework=framework
            )
        except Exception as exc:
            raise AudioError(
                f"wake word model {model_name!r} failed to load: {exc}"
            ) from exc

    def score(self, frame: bytes) -> float:
        """Wake word confidence for this 160 ms frame (0.0-1.0)."""
        samples = self._np.frombuffer(frame, dtype=self._np.int16)
        scores = self._model.predict(samples)
        return float(scores.get(self.model_name, 0.0))


class SileroVAD:
    """Voice activity detector backed by pysilero-vad."""

    _CHUNK_BYTES = 512 * 2  # Silero chunk: 512 samples, 16-bit

    def __init__(self, threshold: float = 0.5) -> None:
        try:
            from pysilero_vad import SileroVoiceActivityDetector
        except ImportError as exc:
            raise AudioError(
                "pysilero-vad is not installed; cannot use VAD"
            ) from exc
        self._vad = SileroVoiceActivityDetector()
        self.threshold = threshold

    def is_speech(self, frame: bytes) -> bool:
        for i in range(0, len(frame), self._CHUNK_BYTES):
            chunk = frame[i : i + self._CHUNK_BYTES]
            if len(chunk) < self._CHUNK_BYTES:
                break
            if self._vad.process_chunk(chunk) >= self.threshold:
                return True
        return False
