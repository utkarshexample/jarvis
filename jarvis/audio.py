"""Audio adapters: AudioSource / AudioSink implementations.

Two flavours of each, swappable by config:

- Device: SounddeviceMic / SounddeviceSpeaker -- real hardware via
  PortAudio. Fail fast with AudioError when no device is present.
- File: FileAudioSource / FileAudioSink -- WAV files. Used for tests
  and for running the loop on a Pi with no mic/speaker attached.

``sounddevice`` is imported lazily inside the device adapters so that
file mode works even where PortAudio is absent. The file adapters
use only the standard library.

Sample-rate contract: FileAudioSource always returns 16 kHz mono
16-bit PCM (resampling / downmixing / width-converting as needed),
because that is what the STT service expects.
"""

from __future__ import annotations

import audioop
import queue
import wave
from pathlib import Path

from .errors import AudioError

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # bytes per sample: 16-bit
CHANNELS = 1  # mono
FRAME_SAMPLES = 2560  # 160 ms at 16 kHz (see ports.py)
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH  # 5120
FRAME_DURATION_S = FRAME_SAMPLES / SAMPLE_RATE  # 0.16


class SounddeviceMic:
    """Real microphone via PortAudio (sounddevice)."""

    def capture(self, seconds: float) -> bytes:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioError(
                "sounddevice is not installed; cannot use the microphone"
            ) from exc
        try:
            recording = sd.rec(
                int(seconds * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            )
            sd.wait()
        except Exception as exc:  # PortAudioError, no device, ...
            raise AudioError(f"microphone capture failed: {exc}") from exc
        return recording.tobytes()

    def stream(self):
        """Yield 160 ms frames until closed (``stream.close()``).

        A bounded queue decouples the PortAudio callback from the
        consumer. The callback never blocks: if the consumer falls
        behind, the oldest frame is dropped. No frame in 5 s means
        the mic died -- fail loudly instead of hanging.
        """
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioError(
                "sounddevice is not installed; cannot use the microphone"
            ) from exc
        frames: queue.Queue = queue.Queue(maxsize=10)

        def _callback(indata, n_frames, time_info, status):
            try:
                if frames.full():
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        pass
                frames.put_nowait(indata.tobytes())
            except queue.Full:
                pass

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            callback=_callback,
        ):
            while True:
                try:
                    yield frames.get(timeout=5)
                except queue.Empty as exc:
                    raise AudioError(
                        "microphone stream stalled (no frame in 5 s)"
                    ) from exc


class SounddeviceSpeaker:
    """Real speaker via PortAudio (sounddevice)."""

    def play(self, audio: bytes, rate: int) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioError(
                "sounddevice is not installed; cannot use the speaker"
            ) from exc
        try:
            import numpy as np

            samples = np.frombuffer(audio, dtype=np.int16)
            sd.play(samples, samplerate=rate)
            sd.wait()
        except Exception as exc:
            raise AudioError(f"speaker playback failed: {exc}") from exc


class FileAudioSource:
    """AudioSource that reads a WAV file (for tests / no-mic setups).

    The WAV may be any rate / channels / width; it is converted to the
    16 kHz mono 16-bit PCM the STT service expects. If the file is
    longer than ``seconds``, only the first ``seconds`` are returned.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load_pcm(self) -> bytes:
        """Whole file as 16 kHz mono 16-bit PCM."""
        if not self.path.exists():
            raise AudioError(f"audio input file not found: {self.path}")
        try:
            with wave.open(str(self.path), "rb") as wav:
                rate = wav.getframerate()
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as exc:
            raise AudioError(f"cannot read WAV {self.path}: {exc}") from exc
        # Convert to mono.
        if channels == 2:
            frames = audioop.tomono(frames, width, 1, 1)
        elif channels != 1:
            raise AudioError(f"unsupported channel count: {channels}")
        # Convert sample width to 16-bit.
        if width != SAMPLE_WIDTH:
            frames = audioop.lin2lin(frames, width, SAMPLE_WIDTH)
        # Resample to 16 kHz.
        if rate != SAMPLE_RATE:
            frames, _ = audioop.ratecv(frames, SAMPLE_WIDTH, 1, rate, SAMPLE_RATE, None)
        return frames

    def capture(self, seconds: float) -> bytes:
        pcm = self._load_pcm()
        return pcm[: int(seconds * SAMPLE_RATE) * SAMPLE_WIDTH]

    def stream(self):
        """Yield 160 ms frames until the file is exhausted."""
        pcm = self._load_pcm()
        for i in range(0, len(pcm), FRAME_BYTES):
            yield pcm[i : i + FRAME_BYTES]


class FileAudioSink:
    """AudioSink that writes PCM to a WAV file (for tests / no-speaker)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def play(self, audio: bytes, rate: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self.path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(rate)
            wav.writeframes(audio)
