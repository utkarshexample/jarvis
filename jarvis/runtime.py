"""Runtime: the conductor.

One state machine, one loop. The runtime owns the *sequence* and
nothing else: it knows nothing about Wyoming, PortAudio, SKILL.md,
or any particular brain. Everything it touches is a port, handed in
by main.py (dependency injection).

States (observable via ``self.state`` -- useful for logging and
debugging; transitions are sequential inside run_once):

    IDLE -> LISTENING -> TRANSCRIBING -> ROUTING -> THINKING
         -> SPEAKING -> IDLE

Error policy: run_once lets JarvisError propagate to the caller, so
tests can assert on failures. run_forever catches JarvisError per
iteration, logs it, and keeps going -- one bad turn never kills the
assistant. Anything that is NOT a JarvisError is a bug and propagates
loudly instead of being swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from .config import Config
from .errors import AudioError, JarvisError
from .ports import AudioSink, AudioSource, Brain, Reflex, Route, STT, TTS
from .skills import SkillRegistry


class State(Enum):
    IDLE = auto()
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
        self.state = State.IDLE

    def run_once(self) -> Turn:
        """One full loop: listen -> transcribe -> route -> think -> speak."""
        # LISTENING
        self.state = State.LISTENING
        audio = self.audio_source.capture(self.config.listen_seconds)
        if not audio:
            raise AudioError("captured no audio")

        # TRANSCRIBING
        self.state = State.TRANSCRIBING
        text = self.stt.transcribe(audio).strip()
        if not text:
            self.state = State.IDLE
            return Turn(text="", reply="", route_kind="silence")

        # ROUTING
        self.state = State.ROUTING
        route: Route = self.reflex.route(text)

        # THINKING
        self.state = State.THINKING
        if route.kind == "skill" and route.skill is not None:
            reply = self.skills.execute(route.skill, text)
        else:
            reply = self.brain.respond(text)

        # SPEAKING
        self.state = State.SPEAKING
        pcm, rate = self.tts.synthesize(reply)
        self.audio_sink.play(pcm, rate)

        self.state = State.IDLE
        return Turn(text=text, reply=reply, route_kind=route.kind)

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
                # Log it and keep going.
                self.log(f"turn failed ({type(exc).__name__}): {exc}")
            except KeyboardInterrupt:
                raise
