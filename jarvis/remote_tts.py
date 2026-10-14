"""Remote + fallback TTS adapters.

RemoteTTS talks to an HTTP voice service:

    POST {url}/speak  with JSON {"text": "..."}
    -> 200 + a 16-bit mono WAV body

Any service satisfying that contract works: a Mac running voice
conversion, a cloud TTS, another Pi. The runtime does not know or
care which one it is -- the URL is configuration, not code.

FallbackTTS wraps a primary TTS and a fallback TTS. It tries the
primary; on any *expected* failure it uses the fallback. The
fallback is the always-works path: if the remote voice module is
down, Jarvis still speaks, in the local voice. Silence is never
the answer to a downed voice service.

Failure cases:
- Remote service down / unreachable -> fallback, no crash.
- Remote service slow -> timeout (config.tts_primary_timeout) -> fallback.
- Remote service returns an error status -> fallback.
- Remote service returns garbage / non-WAV / wrong format -> fallback.
- Both primary AND fallback down -> ServiceUnavailable propagates
  (the runtime logs it and keeps running; see runtime.run_forever).
- A bug in the primary (non-JarvisError) still propagates loudly,
  per the errors.py contract -- the fallback is a safety net for
  expected failures, not a blanket for bugs.
"""

from __future__ import annotations

import io
import sys
import time
import wave
from typing import Callable

import httpx

from .errors import JarvisError, ServiceUnavailable


def _wav_to_pcm(body: bytes) -> tuple[bytes, int]:
    """Parse a 16-bit mono WAV body into (pcm_bytes, sample_rate)."""
    try:
        with wave.open(io.BytesIO(body), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                raise ServiceUnavailable(
                    "remote TTS must return 16-bit mono WAV "
                    f"(got {wav.getsampwidth() * 8}-bit, {wav.getnchannels()} channels)"
                )
            return wav.readframes(wav.getnframes()), wav.getframerate()
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable(f"remote TTS returned unparseable audio: {exc}") from exc


class RemoteTTS:
    """TTS adapter: POSTs text to an HTTP voice service, returns PCM."""

    def __init__(
        self,
        url: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        log: Callable[[str], None] | None = None,
        debug: bool = False,
    ) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._log = log
        self._debug_flag = debug

    def _debug(self, msg: str) -> None:
        if self._debug_flag and self._log is not None:
            self._log(f"[DEBUG] {msg}")

    def synthesize(self, text: str) -> tuple[bytes, int]:
        # "Send data to Rick": the text goes to the Mac RVC API (/speak),
        # the Rick-voice WAV comes back. Logged so the debug trace shows
        # exactly what was sent, what came back, and how long it took.
        self._debug(
            f"TTS: sending to Rick ({self.url}/speak, {len(text)} chars): "
            f"{text[:80]!r}{'...' if len(text) > 80 else ''}"
        )
        t0 = time.monotonic()
        try:
            resp = self._client.post(f"{self.url}/speak", json={"text": text})
        except httpx.HTTPError as exc:
            self._debug(f"TTS: Rick unreachable ({exc})")
            raise ServiceUnavailable(
                f"remote TTS unreachable at {self.url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            self._debug(f"TTS: Rick returned HTTP {resp.status_code}")
            raise ServiceUnavailable(
                f"remote TTS error: HTTP {resp.status_code} from {self.url}"
            )
        pcm, rate = _wav_to_pcm(resp.content)
        self._debug(
            f"TTS: Rick replied ({len(pcm)} bytes PCM, {rate} Hz, "
            f"in {time.monotonic() - t0:.1f}s)"
        )
        return pcm, rate


class FallbackTTS:
    """TTS adapter: primary, with automatic fallback on expected failures."""

    def __init__(
        self,
        primary,
        fallback,
        log: Callable[[str], None] | None = None,
        debug: bool = False,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._log = log
        self._debug_flag = debug

    def _debug(self, msg: str) -> None:
        if self._debug_flag and self._log is not None:
            self._log(f"[DEBUG] {msg}")

    def synthesize(self, text: str) -> tuple[bytes, int]:
        try:
            return self._primary.synthesize(text)
        except JarvisError as exc:
            self._debug(f"TTS: primary failed ({exc}), using fallback (local Piper)")
            print(f"tts fallback: primary failed ({exc}), using fallback", file=sys.stderr)
            return self._fallback.synthesize(text)
