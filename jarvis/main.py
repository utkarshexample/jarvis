"""Composition root: builds everything, starts services, runs.

This is the ONLY place that knows about concrete classes. main.py
reads the Config, constructs the adapters, injects them into the
Runtime, and starts the Wyoming services as subprocesses (pilot
behaviour -- systemd units come later).

Run:  python -m jarvis.main
Stop: Ctrl+C (services are terminated on exit).

The Wyoming services are started with the venv binaries installed by
the setup (see SOFTWARE.md). main.py waits for each service's TCP
port to accept connections before proceeding, so a slow first start
(STT model download) is handled, not fatal. If a service never
comes up, the port wait fails with the tail of that service's log
attached -- that is the first thing to read when startup fails.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from .audio import FileAudioSink, FileAudioSource, SounddeviceMic, SounddeviceSpeaker
from .brains import EchoBrain, MuseBrain
from .config import Config
from .errors import ServiceUnavailable
from .ports import AudioSink, AudioSource, Brain, TTS
from .reflex import RuleReflex
from .runtime import Runtime
from .skills import SkillRegistry
from .wyoming_io import WyomingSTT, WyomingTTS
from .remote_tts import FallbackTTS, RemoteTTS

STT_LOG = Path("/tmp/jarvis-stt.log")
TTS_LOG = Path("/tmp/jarvis-tts.log")


def wait_for_port(port: int, timeout: float, log_path: Path) -> None:
    """Poll until localhost:port accepts a connection, or raise."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            time.sleep(1)
    tail = ""
    try:
        tail = "\n".join(log_path.read_text().splitlines()[-20:])
    except OSError:
        pass
    raise ServiceUnavailable(
        f"service on port {port} did not come up within {timeout}s.\n"
        f"Tail of {log_path}:\n{tail}"
    )


def start_services(config: Config) -> list[subprocess.Popen]:
    """Start the Wyoming STT + TTS services as subprocesses."""
    config.models_path.mkdir(parents=True, exist_ok=True)
    procs: list[subprocess.Popen] = []

    stt_cmd = [
        str(config.stt_bin),
        "--uri",
        f"tcp://127.0.0.1:{config.stt_port}",
        "--model",
        config.stt_model,
        "--data-dir",
        str(config.models_path),
        "--device",
        "cpu",
        "--language",
        config.stt_language,
    ]
    tts_cmd = [
        str(config.tts_bin),
        "--uri",
        f"tcp://127.0.0.1:{config.tts_port}",
        "--voice",
        config.tts_voice,
        "--data-dir",
        str(config.models_path),
    ]
    for cmd, log_path in ((stt_cmd, STT_LOG), (tts_cmd, TTS_LOG)):
        log_file = log_path.open("ab")
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        procs.append(proc)
        # Keep the log file handle alive via the proc object is not
        # possible; the child inherits the fd, so closing ours is safe.
        log_file.close()

    wait_for_port(config.stt_port, timeout=240, log_path=STT_LOG)
    wait_for_port(config.tts_port, timeout=60, log_path=TTS_LOG)
    return procs


def stop_services(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _build_tts(config: Config) -> TTS:
    """Local Piper TTS, or remote-voice-with-local-fallback when configured."""
    local = WyomingTTS(config.tts_uri)
    if not config.tts_primary_url:
        return local
    return FallbackTTS(
        RemoteTTS(config.tts_primary_url, timeout=config.tts_primary_timeout),
        local,
    )


def _build_brain(config: Config) -> Brain:
    """EchoBrain by default; MuseBrain when JARVIS_BRAIN=muse."""
    if config.brain == "muse":
        return MuseBrain(
            socket_path=config.brain_socket or None,
            session_id=config.brain_session_id,
            timeout=config.brain_timeout,
            persona=config.brain_persona,
            fallback=config.brain_fallback,
        )
    return EchoBrain()


def build_runtime(config: Config) -> Runtime:
    """Construct the Runtime with the adapters the config selects."""
    if config.audio_source == "file":
        audio_source: AudioSource = FileAudioSource(config.audio_file)
    else:
        audio_source = SounddeviceMic()

    if config.audio_sink == "file":
        audio_sink: AudioSink = FileAudioSink(config.audio_out_file)
    else:
        audio_sink = SounddeviceSpeaker()

    skills = SkillRegistry.from_directory(config.skills_dir)
    for warning in skills.warnings:
        print(f"skill warning: {warning}", file=sys.stderr)

    return Runtime(
        config=config,
        audio_source=audio_source,
        audio_sink=audio_sink,
        stt=WyomingSTT(config.stt_uri, language=config.stt_language),
        tts=_build_tts(config),
        reflex=RuleReflex(skills),
        brain=_build_brain(config),
        skills=skills,
    )


def main() -> int:
    config = Config.from_env()
    procs: list[subprocess.Popen] = []
    try:
        procs = start_services(config)
        runtime = build_runtime(config)
        runtime.run_forever()
    except KeyboardInterrupt:
        print("\nStopping Jarvis.")
    finally:
        stop_services(procs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
