"""Brains: Brain implementations.

The Brain port is `respond(text) -> str`. Swapping brains is config:
main.py picks which class to construct; the runtime never knows which
one it got.

EchoBrain: repeats the utterance. Proves the wiring without depending
on any cloud service or SDK.

MuseBrain: the Muse Gadgets SDK path. It talks to the already-running
`musegadget run` service over its local Unix socket (the same socket
`musegadget send-user-msg` uses).

CORRECTED MECHANISM (Oct 14, live test): `LinkSession.send_chat`
(POST /chat/stream) returns a DELIVERY RECEIPT, not the assistant
reply: `{"channel", "is_thread", "message_id", "reply_to_message_id",
"session_id"}`. The SDK has no chat-reply event -- the device never
receives the assistant reply text through send_chat. The reply comes
back through the command channel: the assistant writes it to a reply
file (via the gadget file.write / system.run), and MuseBrain polls
for that file. One turn at a time: MuseBrain deletes any stale reply,
sends, then waits for a NEW reply file. See docs/architecture/muse-brain.md.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

DEFAULT_SOCKET = Path("/run/musegadget/musegadget.sock")
# Default: main chat (empty). A side chat needs a UUID session id
# (the server rejects other formats with 400 invalid session_id), but
# v1 uses the main chat: the side chat agent answers in the chat but
# does not write the reply file, so the Pi would time out waiting.
# Side chats are a future option once their agent can write replies.
DEFAULT_SESSION_ID = ""
DEFAULT_TIMEOUT_S = 90.0  # CLI uses 90s; SDK send_chat waits up to 60s
DEFAULT_REPLY_DIR = Path("/tmp/jarvis-replies")
DEFAULT_REPLY_TIMEOUT_S = 120.0  # how long to wait for the assistant reply file
DEFAULT_POLL_INTERVAL_S = 0.5
DEFAULT_FALLBACK = "Sorry, I could not reach my brain right now."

# Protocol appended to EVERY message MuseBrain sends. The assistant that
# receives the turn (main chat or a side chat) may not know the reply-file
# protocol -- it has no shared context with the Pi. So the instruction
# travels with the message: after replying, write the exact reply text to
# the reply file via the gadget file.write. The Pi polls that file and
# speaks it. Without this, the assistant answers in the chat but the Pi
# times out waiting (the side-chat failure of Oct 14).
REPLY_PROTOCOL = (
    "[System: You are answering for a voice assistant on a Raspberry Pi. "
    "After your reply, use the gadget file.write to write your EXACT reply "
    "text (and nothing else) to {reply_path}. The Pi reads that file and "
    "speaks it aloud. Do not mention the file in your reply. "
    "Keep your reply short and speakable.]"
)

# Default persona (Rick-like sparring partner). Overridable via
# JARVIS_BRAIN_PERSONA; set it to "off" for no persona.
DEFAULT_PERSONA = (
    ""
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
    """Brain: send the utterance to Muse, wait for the reply file.

    1. Delete any stale reply file for this session (clean slate).
    2. Send via the musegadget socket; the receipt confirms delivery.
    3. Poll for `<reply_dir>/<session_id>.txt` until it appears or the
       reply timeout expires. The assistant writes it via the gadget
       file.write / system.run (see the assistant protocol in the doc).
    4. Read it, clean it up, return it.

    Failure policy: NEVER silent, NEVER a crash. Any transport failure,
    error receipt, timeout, or empty reply returns the fallback message
    and logs to stderr.
    """

    def __init__(
        self,
        socket_path: str | None = None,
        session_id: str | None = DEFAULT_SESSION_ID,
        timeout: float = DEFAULT_TIMEOUT_S,
        persona: str | None = None,
        fallback: str = DEFAULT_FALLBACK,
        reply_dir: str | None = None,
        reply_timeout: float = DEFAULT_REPLY_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        # SDK env override wins, then explicit path, then the default.
        self.socket_path = Path(
            os.environ.get("MUSEGADGET_SOCKET") or socket_path or DEFAULT_SOCKET
        )
        self.session_id = session_id or ""
        self.timeout = timeout
        self.persona = _resolve_persona(persona)
        self.fallback = fallback
        self.reply_dir = Path(reply_dir or DEFAULT_REPLY_DIR)
        self.reply_timeout = reply_timeout
        self.poll_interval = poll_interval

    def respond(self, text: str) -> str:
        # Reply file: one per session. Empty session (main chat) uses
        # a fixed name so the assistant still has a target.
        name = f"{self.session_id}.txt" if self.session_id else "main.txt"
        reply_path = self.reply_dir / name
        try:
            self.reply_dir.mkdir(parents=True, exist_ok=True)
            reply_path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"muse brain: could not clear reply file ({exc})", file=sys.stderr)
        message = f"{self.persona}\n\nUser: {text}" if self.persona else text
        message += "\n\n" + REPLY_PROTOCOL.format(reply_path=reply_path)
        try:
            receipt = self._send(message)
        except (OSError, TimeoutError, ValueError) as exc:
            print(f"muse brain: send failed ({exc}), using fallback", file=sys.stderr)
            return self.fallback
        if not isinstance(receipt, dict) or not receipt.get("ok"):
            print(f"muse brain: error receipt ({receipt}), using fallback", file=sys.stderr)
            return self.fallback
        return self._wait_for_reply(reply_path)

    def _wait_for_reply(self, reply_path: Path) -> str:
        deadline = time.monotonic() + self.reply_timeout
        while time.monotonic() < deadline:
            try:
                content = reply_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                pass  # not written yet; keep waiting
            except OSError as exc:
                print(f"muse brain: could not read reply file ({exc}), using fallback", file=sys.stderr)
                return self.fallback
            else:
                # File exists. Empty = still being written (or an empty
                # reply); keep waiting until the timeout.
                if content.strip():
                    try:
                        reply_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return content.strip()
            time.sleep(self.poll_interval)
        print(f"muse brain: no reply in {self.reply_timeout}s, using fallback", file=sys.stderr)
        return self.fallback

    def _send(self, message: str) -> dict:
        """Send one message; return the delivery receipt (not the reply)."""
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
