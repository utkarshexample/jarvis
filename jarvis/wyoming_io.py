"""Wyoming adapters: STT / TTS clients speaking the Wyoming protocol.

The Wyoming services (wyoming-faster-whisper, wyoming-piper) are
separate processes. Each one is a TCP server: the client sends JSON
events (one per line) and receives JSON events back; audio travels as
the event payload. The official ``wyoming`` library implements the
wire format -- we use it, we do not hand-roll the protocol.

The ``wyoming`` client is asyncio-based, but the rest of Jarvis is
deliberately synchronous (easier to read, easier to reason about).
So the async code lives ONLY here, inside these two adapters: each
public method is sync and runs one short async session with
``asyncio.run``. The async boundary never leaks into the core.

STT session: Transcribe -> AudioStart -> AudioChunk* -> AudioStop,
then read events until the Transcript arrives.
TTS session: Synthesize, then read AudioChunk events until AudioStop.

Every transport failure is wrapped in ServiceUnavailable so the
runtime can treat "service down" as one handled case.
"""

from __future__ import annotations

import asyncio

from .errors import ServiceUnavailable

CHUNK_BYTES = 960  # 30 ms of 16 kHz mono 16-bit audio


class WyomingSTT:
    """STT adapter: talks to wyoming-faster-whisper over TCP."""

    def __init__(self, uri: str, language: str = "en", timeout: float = 30.0) -> None:
        self.uri = uri
        self.language = language
        self.timeout = timeout

    def transcribe(self, audio: bytes) -> str:
        try:
            return asyncio.run(self._transcribe(audio))
        except (OSError, asyncio.TimeoutError) as exc:
            raise ServiceUnavailable(f"STT service unreachable at {self.uri}: {exc}") from exc

    async def _transcribe(self, audio: bytes) -> str:
        from wyoming.asr import Transcribe, Transcript
        from wyoming.audio import AudioChunk, AudioStart, AudioStop
        from wyoming.client import AsyncClient

        client = AsyncClient.from_uri(
            self.uri, connect_timeout=self.timeout, read_timeout=self.timeout
        )
        async with client:
            await client.write_event(Transcribe(language=self.language).event())
            await client.write_event(
                AudioStart(rate=16000, width=2, channels=1).event()
            )
            for i in range(0, len(audio), CHUNK_BYTES):
                await client.write_event(
                    AudioChunk(
                        rate=16000,
                        width=2,
                        channels=1,
                        audio=audio[i : i + CHUNK_BYTES],
                    ).event()
                )
            await client.write_event(AudioStop().event())
            while True:
                event = await client.read_event()
                if event is None:
                    raise ServiceUnavailable("STT service closed the connection")
                if event.type == "transcript":
                    return Transcript.from_event(event).text
                if event.type == "error":
                    raise ServiceUnavailable(
                        f"STT service error: {event.data.get('text', event.data)}"
                    )
                # Ignore anything else (e.g. info events) and keep reading.


class WyomingTTS:
    """TTS adapter: talks to wyoming-piper over TCP."""

    def __init__(self, uri: str, timeout: float = 30.0) -> None:
        self.uri = uri
        self.timeout = timeout

    def synthesize(self, text: str) -> tuple[bytes, int]:
        try:
            return asyncio.run(self._synthesize(text))
        except (OSError, asyncio.TimeoutError) as exc:
            raise ServiceUnavailable(f"TTS service unreachable at {self.uri}: {exc}") from exc

    async def _synthesize(self, text: str) -> tuple[bytes, int]:
        from wyoming.audio import AudioChunk
        from wyoming.client import AsyncClient
        from wyoming.tts import Synthesize

        client = AsyncClient.from_uri(
            self.uri, connect_timeout=self.timeout, read_timeout=self.timeout
        )
        chunks: list[bytes] = []
        rate = 22050  # fallback; replaced by the first chunk's real rate
        async with client:
            await client.write_event(Synthesize(text=text).event())
            while True:
                event = await client.read_event()
                if event is None:
                    raise ServiceUnavailable("TTS service closed the connection")
                if event.type == "audio-chunk":
                    chunk = AudioChunk.from_event(event)
                    rate = chunk.rate
                    chunks.append(chunk.audio)
                elif event.type == "audio-stop":
                    break
                elif event.type == "error":
                    raise ServiceUnavailable(
                        f"TTS service error: {event.data.get('text', event.data)}"
                    )
                # Ignore anything else and keep reading.
        if not chunks:
            raise ServiceUnavailable("TTS service returned no audio")
        return b"".join(chunks), rate
