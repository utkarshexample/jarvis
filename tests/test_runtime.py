"""Runtime tests: the full loop with fake adapters.

No services, no hardware, no network. The fakes prove the conductor
logic: state transitions, routing, silence handling, error surfacing.
"""

import pytest

from jarvis.brains import EchoBrain
from jarvis.config import Config
from jarvis.errors import ServiceUnavailable
from jarvis.reflex import RuleReflex
from jarvis.runtime import Runtime, State
from jarvis.skills import SkillRegistry


class FakeAudioSource:
    def __init__(self, payload: bytes = b"\x00" * 1600) -> None:
        self.payload = payload
        self.captured_seconds: list[float] = []

    def capture(self, seconds: float) -> bytes:
        self.captured_seconds.append(seconds)
        return self.payload


class FakeAudioSink:
    def __init__(self) -> None:
        self.played: list[tuple[bytes, int]] = []

    def play(self, audio: bytes, rate: int) -> None:
        self.played.append((audio, rate))


class FakeSTT:
    def __init__(self, text: str = "hello") -> None:
        self.text = text

    def transcribe(self, audio: bytes) -> str:
        return self.text


class FakeTTS:
    def synthesize(self, text: str) -> tuple[bytes, int]:
        return (f"pcm:{text}".encode(), 22050)


def _runtime(stt_text: str = "hello", config: Config | None = None) -> Runtime:
    skills = SkillRegistry.from_directory("skills")
    return Runtime(
        config=config or Config(listen_seconds=1.0),
        audio_source=FakeAudioSource(),
        audio_sink=FakeAudioSink(),
        stt=FakeSTT(stt_text),
        tts=FakeTTS(),
        reflex=RuleReflex(skills),
        brain=EchoBrain(),
        skills=skills,
        log=lambda _msg: None,
    )


def test_brain_turn_end_to_end():
    runtime = _runtime("tell me a joke")
    turn = runtime.run_once()
    assert turn.text == "tell me a joke"
    assert turn.route_kind == "brain"
    assert turn.reply == "You said: tell me a joke"
    assert runtime.state is State.IDLE


def test_skill_turn_end_to_end():
    runtime = _runtime("what time is it")
    turn = runtime.run_once()
    assert turn.route_kind == "skill"
    assert turn.reply.startswith("It is ")


def test_silence_produces_no_reply_and_no_speech():
    runtime = _runtime("   ")
    turn = runtime.run_once()
    assert turn.route_kind == "silence"
    assert turn.reply == ""
    assert runtime.audio_sink.played == []


def test_tts_receives_the_reply():
    runtime = _runtime("echo hi")
    runtime.run_once()
    assert runtime.audio_sink.played == [(b"pcm:hi", 22050)]


def test_stt_failure_propagates_to_caller():
    class BrokenSTT:
        def transcribe(self, audio: bytes) -> str:
            raise ServiceUnavailable("stt down")

    skills = SkillRegistry.from_directory("skills")
    runtime = Runtime(
        config=Config(listen_seconds=1.0),
        audio_source=FakeAudioSource(),
        audio_sink=FakeAudioSink(),
        stt=BrokenSTT(),
        tts=FakeTTS(),
        reflex=RuleReflex(skills),
        brain=EchoBrain(),
        skills=skills,
        log=lambda _msg: None,
    )
    with pytest.raises(ServiceUnavailable):
        runtime.run_once()


def test_run_forever_survives_a_bad_turn_then_stops():
    """A JarvisError in one turn is logged; KeyboardInterrupt stops."""
    calls = {"n": 0}

    class FlakySTT:
        def transcribe(self, audio: bytes) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ServiceUnavailable("stt down once")
            raise KeyboardInterrupt

    logs: list[str] = []
    skills = SkillRegistry.from_directory("skills")
    runtime = Runtime(
        config=Config(listen_seconds=1.0),
        audio_source=FakeAudioSource(),
        audio_sink=FakeAudioSink(),
        stt=FlakySTT(),
        tts=FakeTTS(),
        reflex=RuleReflex(skills),
        brain=EchoBrain(),
        skills=skills,
        log=logs.append,
    )
    with pytest.raises(KeyboardInterrupt):
        runtime.run_forever()
    assert any("stt down once" in line for line in logs)
