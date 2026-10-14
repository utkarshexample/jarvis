"""Ports: the contracts every part of Jarvis speaks.

A port is a ``typing.Protocol`` -- an interface with no implementation.
The runtime (the core) only ever talks to ports. The adapters
(audio.py, wyoming_io.py, brains.py, skills.py, wakeword.py) implement
them.

Why this matters: swapping a part means writing a new class that
satisfies the same port. The core never changes. That is what makes
the brain swappable (Echo -> Muse -> OpenAI), the ears swappable
(file -> mic), and the mouth swappable (file -> speaker -> glasses
display) without a rewrite.

Audio contract (shared by every audio adapter):
- PCM is raw bytes: 16-bit little-endian signed integers (``width=2``),
  mono (``channels=1``), at the given sample rate.
- Mic / STT side is always 16 kHz (``Config.sample_rate``).
- Speaker side plays at whatever rate the TTS adapter returns.
- Streaming frames are 2560 samples (160 ms) at 16 kHz = 5120 bytes:
  2x the openWakeWord 1280-sample frame, 5x the Silero VAD 512-sample
  chunk, so one frame feeds both detectors without re-chunking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class Route:
    """The reflex layer's routing decision for one utterance."""

    kind: str  # "skill" or "brain"
    skill: str | None = None  # skill name when kind == "skill"


class AudioSource(Protocol):
    """Something that produces raw PCM audio (ears)."""

    def capture(self, seconds: float) -> bytes:
        """Record ``seconds`` of audio, return 16 kHz mono 16-bit PCM."""
        ...

    def stream(self) -> Iterator[bytes]:
        """Yield 160 ms frames (16 kHz mono 16-bit PCM) until closed.

        The caller closes the iterator (``stream.close()``) when the
        turn ends. A device stream is infinite; a file stream ends
        when the file is exhausted.
        """
        ...


class AudioSink(Protocol):
    """Something that plays raw PCM audio (mouth)."""

    def play(self, audio: bytes, rate: int) -> None:
        """Play PCM audio (16-bit mono) sampled at ``rate`` Hz."""
        ...


class WakeWordDetector(Protocol):
    """Wake word: one frame in, confidence score out."""

    def score(self, frame: bytes) -> float:
        """Wake word confidence for this 160 ms frame (0.0-1.0).

        The runtime compares it to the configured threshold, so the
        detector itself holds no threshold.
        """
        ...


class VAD(Protocol):
    """Voice activity: one frame in, speech or not."""

    def is_speech(self, frame: bytes) -> bool:
        """True when this 160 ms frame contains speech."""
        ...


class STT(Protocol):
    """Speech-to-text: PCM in, transcript out."""

    def transcribe(self, audio: bytes) -> str:
        """Transcribe 16 kHz mono 16-bit PCM. Returns plain text."""
        ...


class TTS(Protocol):
    """Text-to-speech: text in, PCM out."""

    def synthesize(self, text: str) -> tuple[bytes, int]:
        """Return (pcm_bytes, sample_rate). PCM is 16-bit mono."""
        ...


class Reflex(Protocol):
    """Routing policy: where does this utterance go?"""

    def route(self, text: str) -> Route:
        ...


class Brain(Protocol):
    """A brain: open conversation + reasoning. Text in, text out."""

    def respond(self, text: str) -> str:
        ...


class Skill(Protocol):
    """A skill: a named capability with a trigger and a handler."""

    name: str
    description: str
    trigger: str  # phrase that routes an utterance to this skill

    def execute(self, text: str) -> str:
        """Run the skill on the utterance, return the reply text."""
        ...
