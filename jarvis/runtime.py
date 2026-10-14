"""Runtime: the conductor.

One state machine, one loop. The runtime owns the *sequence* and
nothing else: it knows nothing about Wyoming, PortAudio, SKILL.md,
or any particular brain. Everything it touches is a port, handed in
by main.py (dependency injection).

States (observable via ``self.state`` -- useful for logging and
debugging; transitions are sequential inside run_once):

    IDLE -> WAKE -> LISTENING -> TRANSCRIBING -> ROUTING -> THINKING
         -> SPEAKING -> IDLE

WAKE (only when a wake word detector is provided): stream frames
through the detector until the wake word is heard. LISTENING then
records from the SAME stream (no audio lost between wake word and
utterance), with a 1 s pre-roll buffer, until VAD detects silence.
When no VAD is provided, LISTENING falls back to the fixed
``listen_seconds`` capture (the old behaviour, kept for tests).

The transcript has a leading "hey jarvis" stripped (the wake word
itself) before routing, so "Hey Jarvis, what time is it?" routes as
"what time is it?".

Debug logging (``JARVIS_DEBUG=1``): every state transition, the wake
word score + heartbeat, VAD events, and per-stage timings are logged
as ``[DEBUG]`` lines. Off by default (the normal log shows only
``heard:`` / ``turn failed``).

Error policy: run_once lets JarvisError propagate to the caller, so
tests can assert on failures. run_forever catches JarvisError per
iteration, logs it (with the state at failure), and keeps going --
one bad turn never kills the assistant. Anything that is NOT a
JarvisError is a bug and propagates loudly instead of being swallowed.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from .audio import FRAME_DURATION_S
from .config import Config
from .errors import AudioError, JarvisError
from .ports import (
    AudioSink,
    AudioSource,
    Brain,
    Reflex,
    Route,
    STT,
    TTS,
    VAD,
    WakeWordDetector,
)
from .skills import SkillRegistry

PREROLL_S = 1.0  # audio kept before the wake word, prepended to the utterance
_PREROLL_FRAMES = max(1, round(PREROLL_S / FRAME_DURATION_S))
_WAKE_HEARTBEAT_S = 10.0  # WAKE "still listening" log interval


class State(Enum):
    IDLE = auto()
    WAKE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    ROUTING = auto()
    THINKING = auto()
    SPEAKING = auto()


@dataclass(frozen=True)
class Turn:
    """One completed loop iteration: what was heard, where it went."""

    text: str
    reply: str
    route_kind: str  # "skill", "brain", or "silence"


def _strip_wake_word(text: str, model_name: str) -> str:
    """Remove a leading wake word from the transcript.

    The STT transcribes this user's "Jarvis" as "Travis", so strip
    "hey travis" too (otherwise the wake word prefix leaks into the
    brain/skill input).
    """
    words = model_name.replace("_", " ").split()
    if not words:
        return text
    parts = []
    for w in words:
        if w.lower() == "jarvis":
            # STT hears this user's "Jarvis" as "Travis" and "Janice".
            parts.append(r"(jarvis|travis|janice)")
        else:
            parts.append(re.escape(w))
    pattern = r"^(" + r"[\s,.;:!?]+".join(parts) + r"[\s,.;:!?]*)+"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()


class Runtime:
    def __init__(
        self,
        *,
        config: Config,
        audio_source: AudioSource,
        audio_sink: AudioSink,
        stt: STT,
        tts: TTS,
        reflex: Reflex,
        brain: Brain,
        skills: SkillRegistry,
        log: Callable[[str], None] = print,
        wake_word: WakeWordDetector | None = None,
        vad: VAD | None = None,
    ) -> None:
        self.config = config
        self.audio_source = audio_source
        self.audio_sink = audio_sink
        self.stt = stt
        self.tts = tts
        self.reflex = reflex
        self.brain = brain
        self.skills = skills
        self.log = log
        self.wake_word = wake_word
        self.vad = vad
        self.state = State.IDLE

    def _debug(self, msg: str) -> None:
        if self.config.debug:
            self.log(f"[DEBUG] {msg}")

    def _set_state(self, state: State) -> None:
        self.state = state
        self._debug(f"state: {state.name}")

    def run_once(self) -> Turn:
        """One full loop: wake -> listen -> transcribe -> route -> think -> speak."""
        stream = None
        try:
            preroll: list[bytes] = []
            if self.wake_word is not None:
                # WAKE: stream frames until the wake word score clears the threshold.
                self._set_state(State.WAKE)
                self._debug(
                    f"WAKE: waiting for wake word (threshold={self.config.wake_word_threshold})"
                )
                stream = self.audio_source.stream()
                buf: deque = deque(maxlen=_PREROLL_FRAMES)
                detected = False
                max_score = 0.0
                wake_start = time.monotonic()
                last_heartbeat = wake_start
                for frame in stream:
                    buf.append(frame)
                    score = self.wake_word.score(frame)
                    max_score = max(max_score, score)
                    if score >= self.config.wake_word_threshold:
                        self._debug(
                            f"WAKE: wake word detected (score={score:.2f}, "
                            f"threshold={self.config.wake_word_threshold})"
                        )
                        detected = True
                        break
                    now = time.monotonic()
                    if now - last_heartbeat >= _WAKE_HEARTBEAT_S:
                        self._debug(
                            f"WAKE: still listening ({now - wake_start:.0f}s, "
                            f"max score {max_score:.2f})"
                        )
                        last_heartbeat = now
                if not detected:
                    # Stream ended (file mode) without the wake word.
                    self._debug(
                        f"WAKE: stream ended without wake word (max score {max_score:.2f})"
                    )
                    self._set_state(State.IDLE)
                    return Turn(text="", reply="", route_kind="silence")
                preroll = list(buf)

            # LISTENING
            self._set_state(State.LISTENING)
            if self.vad is not None:
                if stream is None:
                    stream = self.audio_source.stream()
                self._debug(f"LISTENING: recording (VAD, preroll {len(preroll)} frames)")
                audio = self._record_vad(stream, preroll)
            else:
                self._debug(
                    f"LISTENING: recording (fixed {self.config.listen_seconds}s)"
                )
                audio = self.audio_source.capture(self.config.listen_seconds)
            if not audio:
                raise AudioError("captured no audio")
            self._debug(
                f"LISTENING: captured {len(audio)} bytes ({len(audio) / 32000:.1f}s)"
            )

            # TRANSCRIBING
            self._set_state(State.TRANSCRIBING)
            t0 = time.monotonic()
            text = self.stt.transcribe(audio).strip()
            if self.wake_word is not None:
                text = _strip_wake_word(text, self.config.wake_word_model)
            self._debug(f"TRANSCRIBING: {text!r} in {time.monotonic() - t0:.1f}s")
            if not text:
                self._set_state(State.IDLE)
                return Turn(text="", reply="", route_kind="silence")

            # ROUTING
            self._set_state(State.ROUTING)
            route: Route = self.reflex.route(text)
            self._debug(f"ROUTING: -> {route.kind} {route.skill or ''}".rstrip())

            # THINKING
            self._set_state(State.THINKING)
            t0 = time.monotonic()
            if route.kind == "skill" and route.skill is not None:
                reply = self.skills.execute(route.skill, text)
                who = f"skill '{route.skill}'"
            else:
                reply = self.brain.respond(text)
                who = f"brain '{self.config.brain}'"
            self._debug(f"THINKING: {who} replied in {time.monotonic() - t0:.1f}s")

            # SPEAKING
            self._set_state(State.SPEAKING)
            t0 = time.monotonic()
            pcm, rate = self.tts.synthesize(reply)
            self._debug(f"SPEAKING: TTS in {time.monotonic() - t0:.1f}s")
            t0 = time.monotonic()
            self.audio_sink.play(pcm, rate)
            self._debug(
                f"SPEAKING: played {len(pcm) / (rate * 2):.1f}s audio "
                f"(took {time.monotonic() - t0:.1f}s)"
            )

            self._set_state(State.IDLE)
            return Turn(text=text, reply=reply, route_kind=route.kind)
        finally:
            if stream is not None:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()

    def _record_vad(self, stream, preroll: list[bytes]) -> bytes:
        """Record from the stream until VAD silence (or the caps)."""
        frames = list(preroll)
        speech_started = False
        silence_frames = 0
        no_speech_frames = 0
        max_frames = round(self.config.listen_max_s / FRAME_DURATION_S)
        for frame in stream:
            frames.append(frame)
            if self.vad is not None and self.vad.is_speech(frame):
                if not speech_started:
                    self._debug("VAD: speech started")
                speech_started = True
                silence_frames = 0
                no_speech_frames = 0
            elif speech_started:
                silence_frames += 1
                if silence_frames * FRAME_DURATION_S >= self.config.vad_silence_s:
                    self._debug(
                        f"VAD: silence {self.config.vad_silence_s}s, utterance end "
                        f"({len(frames) * FRAME_DURATION_S:.1f}s, {len(frames)} frames)"
                    )
                    break
            else:
                # Wake word heard but no speech followed; give up early.
                no_speech_frames += 1
                if no_speech_frames * FRAME_DURATION_S >= self.config.listen_seconds:
                    self._debug(
                        f"VAD: no speech in {self.config.listen_seconds}s after wake word, giving up"
                    )
                    break
            if len(frames) >= max_frames:
                self._debug(
                    f"VAD: utterance capped at {self.config.listen_max_s}s"
                )
                break
        return b"".join(frames)

    def run_forever(self) -> None:
        """Loop until interrupted. One bad turn never kills the assistant."""
        self.log("Jarvis listening. Ctrl+C to stop.")
        while True:
            try:
                turn = self.run_once()
                if turn.route_kind != "silence":
                    self.log(f"heard: {turn.text!r} -> [{turn.route_kind}] {turn.reply!r}")
            except JarvisError as exc:
                # Expected failure (service down, no mic, skill error...).
                # Log it (with the state at failure) and keep going.
                self.log(
                    f"turn failed ({type(exc).__name__}) in state {self.state.name}: {exc}"
                )
            except KeyboardInterrupt:
                raise
