# MuseBrain: the real brain (Muse via the Muse Gadgets SDK)

Status: implemented Oct 14, 2026 (tests pass). Live-test pending.

## What it is

`MuseBrain` implements the `Brain` port (`respond(text) -> str`). It sends
the utterance to Muse through the already-running `musegadget run`
service and returns Muse reply. Swapping brains is config:
`JARVIS_BRAIN=echo` (default, test brain) or `JARVIS_BRAIN=muse`.

## The mechanism (from reading the SDK source + a live test)

- The `musegadget run` service holds the connection to Muse. It is the
  daemon; Jarvis does not run another one.
- The SDK call underneath is `LinkSession.send_chat` (`POST /chat/stream`).
  It returns a DELIVERY RECEIPT, not the assistant reply:
  `{"channel", "is_thread", "message_id", "reply_to_message_id", "session_id"}`.
  The SDK has no chat-reply event -- the device never receives the
  assistant reply text through send_chat. (An earlier draft of this doc
  claimed send_chat returns the reply. The Oct 14 live test proved that
  wrong: the response was a receipt.)
- The reply comes back through the command channel: the assistant writes
  it to a reply file (via the gadget `file.write` / `system.run`), and
  MuseBrain polls for that file.
- Jarvis talks to the service over its local Unix socket
  (`/run/musegadget/musegadget.sock`, overridable via the
  `MUSEGADGET_SOCKET` env var): one JSON line in
  (`{"message", "session_id"}`), one JSON line back (the receipt).
- The reverse direction (Muse -> Pi) is a separate channel: Muse can
  invoke `system.run`, `file.read`, `file.write`, `device.health` on the
  Pi through the SDK Executor, run as an unprivileged account. The reply
  file uses that channel.

## Contract

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| Brain | `JARVIS_BRAIN` | `echo` | `muse` = real brain, anything else = EchoBrain |
| Session | `JARVIS_BRAIN_SESSION_ID` | empty (main chat) | Empty = main chat (v1). A side chat needs a UUID -- the server rejects other formats with 400 invalid session_id |
| Socket | `JARVIS_BRAIN_SOCKET` | SDK default | musegadget socket path |
| Send timeout | `JARVIS_BRAIN_TIMEOUT` | `90` (s) | Socket wait for the receipt. Must exceed the SDK 60s send_chat timeout |
| Reply dir | `JARVIS_BRAIN_REPLY_DIR` | `/tmp/jarvis-replies` | Where the assistant writes reply files |
| Reply timeout | `JARVIS_BRAIN_REPLY_TIMEOUT` | `120` (s) | How long to wait for the reply file |
| Persona | `JARVIS_BRAIN_PERSONA` | Rick-like default | Prepended to every message. `off` = none |
| Fallback | `JARVIS_BRAIN_FALLBACK` | "Sorry, I could not reach my brain right now." | Spoken when the brain is unreachable |

Session routing (v1 = main chat): a side chat sounds tidier, but it
breaks the loop. The Oct 14 live test proved it: the side chat agent
DID answer ("Just idling at full capacity..."), but it answered only in
the chat -- it did not write the reply file, so the Pi timed out after
120s. The side chat agent has no reply-file protocol and no Pi access.
The main chat is the closed loop: the Muse in the main chat sees the
Jarvis turn, answers it, and writes the reply file. So v1 sends to the
main chat (empty session id, reply file `main.txt`). A dedicated side
chat is a future option once its agent can write replies. (A plain-word
session id like "jarvis" gets `400 invalid session_id`; a UUID is
accepted. The test side chat UUID was
`a9019477-ae47-57a4-a5cb-c4166ecb8708`.)

Reply protocol (one turn at a time):
1. MuseBrain deletes any stale `<session_id>.txt` (clean slate) and
   creates the reply dir.
2. It sends the message; the receipt confirms delivery.
3. It polls for `<reply_dir>/<session_id>.txt` every 0.5s until it
   appears (non-empty) or the reply timeout expires.
4. It reads the file, deletes it, returns the content.

Assistant protocol (how the Muse delivers the reply): when answering in
the Jarvis side chat, also write the reply text to
`<reply_dir>/<session_id>.txt` via the gadget `file.write` (atomic
replace) or `system.run`. One reply per turn. The reply file is
transient (in /tmp, cleared on reboot).

Persona: the side chat has no persistent instructions, so MuseBrain
prepends the persona to every message (`<persona>\\n\\nUser: <text>`).
The default persona is the Rick-like sparring partner (god complex,
hard to persuade, concede condition, direct answers for factual
questions, short enough to speak aloud). It is a default, not a
hardcode: `JARVIS_BRAIN_PERSONA` replaces it, `off` disables it.

## Failure cases

| Failure | Behaviour |
|---|---|
| musegadget service down / socket missing | Connection error -> fallback message, logged to stderr |
| Receipt not ok (e.g. 400 invalid session_id) | Fallback message, logged |
| No reply file within the reply timeout | Fallback message, logged |
| Reply file empty | Kept waiting (still being written) until the timeout -> fallback |
| Reply file unreadable (permissions) | Fallback message, logged |
| MuseBrain itself throws a bug (non-transport) | Propagates (per errors.py: bugs are loud, not swallowed) |

Never silent, never a crash: every expected failure speaks the fallback
message and keeps the runtime looping.

## Live test plan

1. On the Pi: `JARVIS_BRAIN=muse ~/.venvs/jarvis-runtime/bin/python -u -m jarvis.main`
2. Say a test line near the JBL (an open question, not "what time is it").
3. The turn appears in the Jarvis side chat; the Muse answers there AND
   writes the reply to the reply file.
4. Jarvis speaks the reply. Verify: the spoken reply is the Muse answer
   (not the fallback), and the log shows `heard: ... -> [brain] ...`.
5. Fallback test: stop the musegadget service (or do not write a reply
   file), speak, confirm Jarvis says the fallback message (then restart
   the service).
