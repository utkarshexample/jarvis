"""Configuration.

One dataclass, built from environment variables with sane defaults.
Nothing else in the codebase reads env vars or hardcodes a port --
``main`` builds a Config and passes it down. That keeps the whole
runtime testable: tests just construct a Config with whatever values
they need.

Env vars (all optional, all prefixed JARVIS_):

- JARVIS_STT_PORT, JARVIS_TTS_PORT -- Wyoming service ports.
- JARVIS_STT_MODEL, JARVIS_STT_LANGUAGE, JARVIS_TTS_VOICE.
- JARVIS_MODELS_DIR -- where voice + STT models live.
- JARVIS_LISTEN_SECONDS -- fixed listen window for pilot v1.
- JARVIS_TTS_PRIMARY_URL -- HTTP voice service (POST /speak -> WAV).
  Empty (default) means local Piper only. When set, the primary is
  tried first and local Piper is the fallback.
- JARVIS_TTS_PRIMARY_TIMEOUT -- seconds to wait for the primary voice.
- JARVIS_AUDIO_SOURCE -- "device" (mic) or "file" (test WAV).
- JARVIS_AUDIO_FILE -- input WAV when source is "file".
- JARVIS_AUDIO_SINK -- "device" (speaker) or "file" (output WAV).
- JARVIS_AUDIO_OUT_FILE -- output WAV when sink is "file".
- JARVIS_SKILLS_DIR -- where SKILL.md skill folders live.
- JARVIS_BRAIN -- "echo" (default, test brain) or "muse" (real brain).
- JARVIS_BRAIN_SESSION_ID -- side chat for MuseBrain. Empty (default) =
  main chat. A side chat needs a UUID (the server rejects other formats),
  but v1 uses the main chat (see the doc).
- JARVIS_BRAIN_REPLY_DIR -- where the assistant writes reply files.
- JARVIS_BRAIN_REPLY_TIMEOUT -- seconds to wait for the reply file (default 120).
- JARVIS_BRAIN_SOCKET -- musegadget socket path (default: the SDK socket).
- JARVIS_BRAIN_TIMEOUT -- seconds to wait for a Muse reply (default 90).
- JARVIS_BRAIN_PERSONA -- persona prompt prepended to each message.
  Unset = default Rick-like persona; "off" = no persona.
- JARVIS_BRAIN_FALLBACK -- what Jarvis says when the brain is unreachable.
- JARVIS_WAKE_WORD_ENABLED -- "true" (default) gates turns on "Hey Jarvis".
  "false" = always-listening (old behaviour).
- JARVIS_WAKE_WORD_MODEL -- openWakeWord model name (default "hey_jarvis").
- JARVIS_WAKE_WORD_THRESHOLD -- detection score 0.0-1.0 (default 0.10,
  tuned: his 'Hey Jarvis' scores ~0.30, background ~0.17). Raise if false
  positives, lower if it misses.
- JARVIS_VAD_SILENCE_S -- silence after speech that ends the utterance (default 1.0).
- JARVIS_LISTEN_MAX_S -- cap on one utterance (default 30).
- JARVIS_DEBUG -- "true" = detailed [DEBUG] log lines (state transitions,
  wake word score + heartbeat, VAD events, per-stage timings). Default off.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    stt_port: int = 10300
    tts_port: int = 10200
    stt_model: str = "tiny"
    stt_language: str = "en"
    tts_voice: str = "en_US-lessac-medium"
    tts_primary_url: str = ""
    tts_primary_timeout: float = 10.0
    models_dir: str = "~/jarvis-models"
    listen_seconds: float = 5.0
    sample_rate: int = 16000
    audio_source: str = "device"
    audio_file: str = ""
    audio_sink: str = "device"
    audio_out_file: str = "/tmp/jarvis-out.wav"
    skills_dir: str = "skills"
    skills_dir: str = "skills"
    brain: str = "echo"
    brain_session_id: str = ""
    brain_socket: str = ""
    brain_timeout: float = 90.0
    brain_persona: str | None = None
    brain_reply_dir: str = "/tmp/jarvis-replies"
    brain_reply_timeout: float = 120.0
    brain_fallback: str = "Sorry, I could not reach my brain right now."
    brain_fallback: str = "Sorry, I could not reach my brain right now."
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.10  # tuned: his 'Hey Jarvis' scores ~0.30, background ~0.17
    vad_silence_s: float = 1.0
    listen_max_s: float = 30.0
    listen_max_s: float = 30.0
    debug: bool = False

    @property
    def stt_uri(self) -> str:
        return f"tcp://127.0.0.1:{self.stt_port}"

    @property
    def tts_uri(self) -> str:
        return f"tcp://127.0.0.1:{self.tts_port}"

    @property
    def models_path(self) -> Path:
        return Path(self.models_dir).expanduser()

    @property
    def stt_bin(self) -> Path:
        return Path.home() / ".venvs" / "jarvis-stt" / "bin" / "wyoming-faster-whisper"

    @property
    def tts_bin(self) -> Path:
        return Path.home() / ".venvs" / "jarvis-tts" / "bin" / "wyoming-piper"

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from JARVIS_* env vars, falling back to defaults."""
        env = os.environ

        def _int(name: str, default: int) -> int:
            try:
                return int(env.get(name, default))
            except ValueError:
                return default

        def _bool(name: str, default: bool) -> bool:
            return env.get(name, str(default)).strip().lower() in ("1", "true", "yes")

        def _float(name: str, default: float) -> float:
            try:
                return float(env.get(name, default))
            except ValueError:
                return default

        return cls(
            stt_port=_int("JARVIS_STT_PORT", 10300),
            tts_port=_int("JARVIS_TTS_PORT", 10200),
            stt_model=env.get("JARVIS_STT_MODEL", "tiny"),
            stt_language=env.get("JARVIS_STT_LANGUAGE", "en"),
            tts_voice=env.get("JARVIS_TTS_VOICE", "en_US-lessac-medium"),
            tts_primary_url=env.get("JARVIS_TTS_PRIMARY_URL", ""),
            tts_primary_timeout=_float("JARVIS_TTS_PRIMARY_TIMEOUT", 10.0),
            models_dir=env.get("JARVIS_MODELS_DIR", "~/jarvis-models"),
            listen_seconds=_float("JARVIS_LISTEN_SECONDS", 5.0),
            audio_source=env.get("JARVIS_AUDIO_SOURCE", "device"),
            audio_file=env.get("JARVIS_AUDIO_FILE", ""),
            audio_sink=env.get("JARVIS_AUDIO_SINK", "device"),
            audio_out_file=env.get("JARVIS_AUDIO_OUT_FILE", "/tmp/jarvis-out.wav"),
            skills_dir=env.get("JARVIS_SKILLS_DIR", "skills"),
            brain=env.get("JARVIS_BRAIN", "echo"),
            brain_session_id=env.get("JARVIS_BRAIN_SESSION_ID", ""),
            brain_socket=env.get("JARVIS_BRAIN_SOCKET", ""),
            brain_timeout=_float("JARVIS_BRAIN_TIMEOUT", 90.0),
            brain_persona=env.get("JARVIS_BRAIN_PERSONA"),
            brain_reply_dir=env.get("JARVIS_BRAIN_REPLY_DIR", "/tmp/jarvis-replies"),
            brain_reply_timeout=_float("JARVIS_BRAIN_REPLY_TIMEOUT", 120.0),
            wake_word_enabled=_bool("JARVIS_WAKE_WORD_ENABLED", True),
            wake_word_model=env.get("JARVIS_WAKE_WORD_MODEL", "hey_jarvis"),
            wake_word_threshold=_float("JARVIS_WAKE_WORD_THRESHOLD", 0.10),
            vad_silence_s=_float("JARVIS_VAD_SILENCE_S", 1.0),
            listen_max_s=_float("JARVIS_LISTEN_MAX_S", 30.0),
            debug=_bool("JARVIS_DEBUG", False),
            brain_fallback=env.get(
                "JARVIS_BRAIN_FALLBACK",
                "Sorry, I could not reach my brain right now.",
            ),
        )
