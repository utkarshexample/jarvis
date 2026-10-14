# MuseBrain: the real brain (Muse via the Muse Gadgets SDK)

Status: implemented Oct 14, 2026 (tests pass). Live-test pending:
the exact `response` shape is confirmed by one live turn.

## What it is

`MuseBrain` implements the `Brain` port (`respond(text) -> str`). It sends
the utterance to Muse through the already-running `musegadget run`
service and returns Muse reply. Swapping brains is config:
`JARVIS_BRAIN=echo` (default, test brain) or `JARVIS_BRAIN=muse`.

## The mechanism (from reading the SDK source, not from guessing)

- The `musegadget run` service holds the connection to Muse. It is the
  daemon; Jarvis does not run another one.
- The SDK call underneath is `LinkSession.send_chat` (`POST /chat/stream`).
  It IS synchronous request/reply: send the message, wait for the reply
  (service-side timeout 60s), return `{"ok", "status", "response"}`.
  Correlation is handled inside the SDK (stream id + future).
- The `send-user-msg` CLI discards the reply (prints only "Sent to your
  Muse"), which is why the link looked one-way. It is not.
- Jarvis talks to the service over its local Unix socket
  (`/run/musegadget/musegadget.sock`, overridable via the
  `MUSEGADGET_SOCKET` env var), the same socket the CLI uses:
  one JSON line in (`{"message", "session_id"}`), one JSON line back.
- The reverse direction (Muse -> Pi) is a separate channel: Muse can
  invoke `system.run`, `file.read`, `file.write`, `device.health` on the
  Pi through the SDK Executor, run as an unprivileged account. MuseBrain
  does not use it; it is noted here because it is how Muse could act on
  the Pi without SSH.

## Contract

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| Brain | `JARVIS_BRAIN` | `echo` | `muse` = real brain, anything else = EchoBrain |
| Session | `JARVIS_BRAIN_SESSION_ID` | `jarvis` | Dedicated side chat. Empty = main chat |
| Socket | `JARVIS_BRAIN_SOCKET` | SDK default | musegadget socket path |
| Timeout | `JARVIS_BRAIN_TIMEOUT` | `90` (s) | Socket wait. Must exceed the SDK 60s send_chat timeout |
| Persona | `JARVIS_BRAIN_PERSONA` | Rick-like default | Prepended to every message. `off` = none |
| Fallback | `JARVIS_BRAIN_FALLBACK` | "Sorry, I could not reach my brain right now." | Spoken when the brain is unreachable |

Session routing: a fixed session id (`jarvis`) keeps Jarvis turns out
of the main chat. The side chat is Jarvis private channel to Muse.

Persona: the side chat has no persistent instructions, so MuseBrain
prepends the persona to every message (`<persona>\\n\\nUser: <text>`).
The default persona is the Rick-like sparring partner (god complex,
hard to persuade, concede condition, direct answers for factual
questions, short enough to speak aloud). It is a default, not a
hardcode: `JARVIS_BRAIN_PERSONA` replaces it, `off` disables it.

Response parsing: `response` is accepted as a plain string, or a dict
with a `text` / `response` / `message` / `content` / `reply` key, or a
list of strings. Anything else -> fallback. The live test confirms
which shape the service actually returns; the parser is tightened then.

## Failure cases

| Failure | Behaviour |
|---|---|
| musegadget service down / socket missing | Connection error -> fallback message, logged to stderr |
| Muse does not reply within timeout | Socket timeout -> fallback message, logged |
| Service returns `ok: false` | Fallback message, logged |
| Reply empty / unrecognised shape | Fallback message, logged |
| MuseBrain itself throws a bug (non-transport) | Propagates (per errors.py: bugs are loud, not swallowed) |

Never silent, never a crash: every expected failure speaks the fallback
message and keeps the runtime looping.

## Live test plan

1. On the Pi: `JARVIS_BRAIN=muse ~/.venvs/jarvis-runtime/bin/python -u -m jarvis.main`
2. Say a test line near the JBL (e.g. "What time is it?" then an open
   question like "Is my plan sound?").
3. The turn appears in the `jarvis` side chat; Muse answers there; the
   reply flows back and Jarvis speaks it.
4. Verify: the spoken reply is Muse answer (not the fallback), and the
   log shows `heard: ... -> [brain] ...`.
5. Confirm the `response` shape from the log / socket reply; tighten
   `_extract_text` if the shape differs from the handled cases.
6. Fallback test: stop the musegadget service, speak, confirm Jarvis
   says the fallback message (then restart the service).
