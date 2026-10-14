"""Brains: Brain implementations.

The Brain port is `respond(text) -> str`. Swapping brains is config:
main.py picks which class to construct; the runtime never knows which
one it got.

EchoBrain: repeats the utterance. Proves the wiring without depending
on any cloud service or SDK.

MuseBrain: the Muse Gadgets SDK path. It talks to the already-running
`musegadget run` service over its local Unix socket (the same socket
`musegadget send-user-msg` uses). The SDK call underneath is
`LinkSession.send_chat` (POST /chat/stream), which IS synchronous
request/reply: it sends the message, waits for Muse reply, and
returns it. The `send-user-msg` CLI discards that reply (it prints
only "Sent to your Muse"), which is why the link looked one-way --
it is not. No separate daemon listener and no request/reply
correlation are needed in Jarvis: the SDK already does both.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

DEFAULT_SOCKET = Path("/run/musegadget/musegadget.sock")
DEFAULT_SESSION_ID = "jarvis"  # dedicated side chat; empty = main chat
DEFAULT_TIMEOUT_S = 90.0  # CLI uses 90s; SDK send_chat waits up to 60s
DEFAULT_FALLBACK = "Sorry, I could not reach my brain right now."

# Default persona (Rick-like sparring partner). Overridable via
# JARVIS_BRAIN_PERSONA; set it to "off" for no persona.
DEFAULT_PERSONA = (
    "You are Jarvis, a one-of-one senior software engineer and a friend. "
    "You have a god complex: you do not accept mistakes automatically, you "
    "are hard to persuade, and you only concede to airtight reasoning. "
    "When you disagree, say exactly what evidence would change your mind, "
    "and concede cleanly when that evidence lands. You are a sparring "
    "partner for brainstorming, not a wall. For factual questions, answer "
    "directly with no persona. Keep replies short enough to speak aloud."
)


def _resolve_persona(raw: str | None) -> str:
    if raw is None:
        return DEFAULT_PERSONA
    if raw.strip().lower() == "off":
        return ""
    return raw


class EchoBrain:
    """Test brain: repeats the utterance back. Proves the wiring."""

    def respond(self, text: str) -> str:
        return f"You said: {text}"


class MuseBrain:
    """Brain: sends the utterance to Muse via the musegadget service.

    Protocol (mirrors `musegadget send-user-msg`): one JSON line to the
    local Unix socket, ``{"message": ..., "session_id": ...}``, one JSON
    line back: ``{"ok": ..., "status": ..., "response": ...}``. The
    ``response`` field carries Muse reply.

    Failure policy: NEVER silent, NEVER a crash. Any transport failure,
    timeout, error reply, or empty reply returns the fallback message,
    so Jarvis always speaks. The failure is logged to stderr so the
    log shows what went wrong.
    """

    def __init__(
        self,
        socket_path: str | None = None,
        session_id: str | None = DEFAULT_SESSION_ID,
        timeout: float = DEFAULT_TIMEOUT_S,
        persona: str | None = None,
        fallback: str = DEFAULT_FALLBACK,
    ) -> None:
        # SDK env override wins, then explicit path, then the default.
        self.socket_path = Path(
            os.environ.get("MUSEGADGET_SOCKET") or socket_path or DEFAULT_SOCKET
        )
        self.session_id = session_id or ""
        self.timeout = timeout
        self.persona = _resolve_persona(persona)
        self.fallback = fallback

    def respond(self, text: str) -> str:
        message = f"{self.persona}\n\nUser: {text}" if self.persona else text
        try:
            reply = self._send(message)
        except (OSError, TimeoutError, ValueError) as exc:
            print(f"muse brain: transport failed ({exc}), using fallback", file=sys.stderr)
            return self.fallback
        if not isinstance(reply, dict) or not reply.get("ok"):
            print(f"muse brain: error reply ({reply}), using fallback", file=sys.stderr)
            return self.fallback
        return self._extract_text(reply.get("response"))

    def _send(self, message: str) -> dict:
        request: dict = {"message": message}
        if self.session_id:
            request["session_id"] = self.session_id
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
            sock.sendall(json.dumps(request).encode() + b"\n")
            line = sock.makefile("rb").readline()
        if not line:
            raise ValueError("empty reply from musegadget service")
        return json.loads(line)

    def _extract_text(self, response) -> str:
        # The reply shape is confirmed by the live test; handle the
        # common shapes defensively until then.
        if isinstance(response, str) and response.strip():
            return response
        if isinstance(response, dict):
            for key in ("text", "response", "message", "content", "reply"):
                value = response.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            parts = response.get("parts") or response.get("messages")
            if isinstance(parts, list):
                texts = [p for p in parts if isinstance(p, str) and p.strip()]
                if texts:
                    return "\n".join(texts)
        if isinstance(response, list):
            texts = [p for p in response if isinstance(p, str) and p.strip()]
            if texts:
                return "\n".join(texts)
        print(f"muse brain: unrecognised reply shape ({type(response)}), using fallback", file=sys.stderr)
        return self.fallback
