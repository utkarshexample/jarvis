"""Config tests: defaults + env overrides."""

import os

from jarvis.config import Config


def test_defaults():
    config = Config()
    assert config.stt_port == 10300
    assert config.tts_port == 10200
    assert config.stt_uri == "tcp://127.0.0.1:10300"
    assert config.tts_uri == "tcp://127.0.0.1:10200"
    assert config.audio_source == "device"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("JARVIS_STT_PORT", "11111")
    monkeypatch.setenv("JARVIS_AUDIO_SOURCE", "file")
    monkeypatch.setenv("JARVIS_AUDIO_FILE", "/tmp/in.wav")
    config = Config.from_env()
    assert config.stt_port == 11111
    assert config.stt_uri == "tcp://127.0.0.1:11111"
    assert config.audio_source == "file"
    assert config.audio_file == "/tmp/in.wav"


def test_bad_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("JARVIS_STT_PORT", "not-a-port")
    assert Config.from_env().stt_port == 10300
    assert "JARVIS_STT_PORT" in os.environ  # sanity: env was set
