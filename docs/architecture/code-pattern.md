# Code pattern: Ports & Adapters

The runtime's code pattern is **Ports & Adapters** (also called Hexagonal
Architecture), with an explicit state machine and manual dependency
injection. This document is the detailed pattern: what it is, why it
fits Jarvis, how each file fits, and how to extend it.

## 1. The pattern in one paragraph

The core of Jarvis -- the loop that listens, routes, thinks, and speaks
-- depends only on **interfaces** (ports), never on concrete libraries
or hardware. Each interface has one or more **adapters** that implement
it: a real one (Wyoming STT, sounddevice mic) and a test one (fake STT,
file audio). `main.py` is the composition root: it picks the adapters
and wires them into the core. Nothing else in the codebase constructs
a dependency.

```
           +------------------- core -------------------+
           |  runtime.py (state machine)                  |
           |  reflex.py (routing policy)                  |
           |  skills.py (skill registry)                   |
           |  ports.py (interfaces)  config.py  errors.py  |
           +---^----^----^----^----^----^----^----^------+
               |    |    |    |    |    |    |    |
  adapters:  audio.py  wyoming_io.py  brains.py  skills.py (handlers)
             (mic/speaker/file) (STT/TTS) (echo)  (time/echo)
```

## 2. Why this pattern for Jarvis

| Jarvis goal | What the pattern gives you |
|---|---|
| Swap brains (Muse / OpenAI / local) | New class implementing `Brain`. Core untouched. |
| Swap ears/mouth (mic / file / glasses) | New class implementing `AudioSource` / `AudioSink`. |
| One skill crash must not kill the runtime | Skills run behind the registry; a `SkillError` is one handled case. |
| Test without hardware | Fakes implement the same ports. `tests/` run with zero services. |
| Learn the system | Each file is one idea. You can read the core without knowing Wyoming. |

The alternative -- the core importing `faster_whisper`, `sounddevice`,
`httpx` directly -- would couple every decision to a library. Swapping
a brain would mean editing the loop. That is exactly the "everything
already written, can't fix it" trap this project is practising against.

## 3. Module map

| File | Responsibility | Depends on |
|---|---|---|
| `jarvis/ports.py` | The contracts: `AudioSource`, `AudioSink`, `STT`, `TTS`, `Reflex`, `Brain`, `Skill`, `Route` | nothing (stdlib only) |
| `jarvis/config.py` | One frozen `Config` dataclass; `from_env()` reads `JARVIS_*` vars | stdlib |
| `jarvis/errors.py` | Typed errors, one per failure mode | nothing |
| `jarvis/runtime.py` | The conductor: state machine + `run_once` / `run_forever` | ports, config, errors |
| `jarvis/reflex.py` | Routing policy (`RuleReflex` now, `JevReflex` in v2) | ports, skills |
| `jarvis/skills.py` | SKILL.md loading, registry, skill handlers | ports, errors, yaml |
| `jarvis/brains.py` | Brain implementations (`EchoBrain` in v1) | nothing |
| `jarvis/audio.py` | Audio adapters: device (sounddevice) + file (WAV) | errors, audioop/wave |
| `jarvis/wyoming_io.py` | Wyoming STT/TTS clients (async contained here) | errors, wyoming lib |
| `jarvis/main.py` | Composition root: builds everything, starts services | everything |

Rules:

- `ports.py`, `config.py`, `errors.py` import nothing from Jarvis. They
  are the stable foundation.
- `runtime.py` imports only ports/config/errors. It must never import
  `sounddevice`, `wyoming`, `httpx`, or any hardware/cloud library.
  If you catch yourself adding such an import to `runtime.py`, that
  code belongs in an adapter.
- `main.py` is the only file that constructs concrete adapters.

## 4. The ports (contracts)

See `jarvis/ports.py` for the exact signatures. The shared audio
contract, which every audio adapter must honour:

- PCM is raw bytes: 16-bit little-endian signed ints (`width=2`),
  mono (`channels=1`).
- Mic / STT side is always 16 kHz (`Config.sample_rate`).
- Speaker side plays at whatever rate the TTS adapter returns.

`Route` is the reflex layer's answer: `kind="skill"` (with
`skill=<name>`) or `kind="brain"`. The runtime does not decide
routing; it follows the Route.

## 5. The state machine

`Runtime` holds an explicit `State`:

```
IDLE -> LISTENING -> TRANSCRIBING -> ROUTING -> THINKING -> SPEAKING -> IDLE
```

Transitions are sequential inside `run_once()` -- there is no
concurrency in v1, so there is no race to reason about. The state is
observable (`runtime.state`) for logging and debugging, and `run_once`
returns a `Turn` (transcribed text, reply, route kind) so tests and
callers can assert on a whole iteration.

`run_forever()` wraps `run_once()` in a loop:

- `JarvisError` (expected failure: service down, no mic, skill error)
  is logged and the loop continues. One bad turn never kills Jarvis.
- Anything else is a bug: it propagates loudly. We never swallow
  unexpected exceptions to "keep running" -- that hides bugs.

## 6. The async boundary

The `wyoming` client library is asyncio-based. The rest of Jarvis is
deliberately synchronous: a sequential pipeline (listen -> transcribe
-> think -> speak) does not need concurrency, and sync code is easier
to read, test, and debug.

So the async code lives **only** in `wyoming_io.py`. Each public method
(`transcribe`, `synthesize`) is sync and runs one short async session
with `asyncio.run()`: connect, exchange events, disconnect, return.
The async boundary never leaks into the core. If you ever need a
second async library, the same rule applies: contain it in its adapter.

## 7. Config and the composition root

- `Config` is a frozen dataclass. `from_env()` reads `JARVIS_*` env
  vars with defaults; bad values fall back to defaults (tested).
- No module except `main.py` reads env vars or constructs adapters.
- `main.py` also owns service management in v1: it starts
  `wyoming-faster-whisper` and `wyoming-piper` as subprocesses, waits
  for their TCP ports (STT gets 240s -- first start downloads the
  model), and terminates them on exit. Systemd units replace this in
  a later milestone; the Runtime does not care either way.

## 8. Skills

A skill is a contract + a handler, kept separate:

- Contract: `skills/<name>/SKILL.md` with YAML frontmatter
  (`name`, `description`, `when`, `inputs`, `outputs`, `permissions`).
  `when` is the v1 trigger phrase, matched as a substring.
- Handler: a Python function `(text) -> reply` in `HANDLERS`
  (`skills.py`). A SKILL.md whose name has no handler is skipped with
  a warning -- never a crash.

v2 moves handlers into the skill's own folder (`handler.py` per
skill), making skills fully drop-in. The registry and frontmatter
format do not change.

v1 skills: `time` (local clock, works offline), `echo` (proves the
skill path). Both are covered by `tests/test_skills.py`.

## 9. Testing strategy

- **No hardware, no services, no network.** Tests use fakes that
  implement the same ports (`tests/test_runtime.py`).
- `tests/` has no `__init__.py` on purpose: pytest inserts the repo
  root into `sys.path`, so `import jarvis` works from the repo root.
- What is covered: routing (reflex), skill loading/execution, config
  defaults + env overrides, the full loop with fakes (brain turn,
  skill turn, silence, TTS wiring), STT failure propagation, and
  `run_forever` surviving a bad turn.
- The real services are verified separately, on the Pi, with the
  file-audio loop test (see §11).

## 10. Extension points (how to add things)

- **New brain:** implement `Brain` (`respond(text) -> str`), pick it
  in `main.build_runtime`. One class, zero core changes.
- **New skill:** add `skills/<name>/SKILL.md` + a handler in
  `HANDLERS`. No other file changes.
- **New input (e.g. glasses camera, wake-word mic):** implement
  `AudioSource` (or a new input port). The runtime does not care
  where audio comes from.
- **New output (e.g. glasses display):** implement `AudioSink` -- or,
  when output is visual rather than audio, a new `Display` port with
  the same shape. The "display card" idea from the glasses discussion
  slots in here: the brain produces a reply, and the output adapter
  decides whether it becomes speech, lens text, or both.
- **New reflex (Jev):** implement `Reflex` (`route(text) -> Route`)
  calling the Jev API. `RuleReflex` and `JevReflex` are interchangeable.

## 11. v1 limits (deliberate)

- Fixed listen window (`JARVIS_LISTEN_SECONDS`, default 5s) instead
  of voice-activity detection. VAD (`pysilero-vad` is installed)
  comes in v2.
- No wake word. The pilot listens on demand / on a loop.
- Brain is `EchoBrain`. MuseBrain is a v2 milestone: `musegadget
  send-user-msg` is one-way, so the reply path needs a listener for
  daemon replies plus request/reply correlation. That is a real
  async integration, not a one-line call.
- Services are subprocesses started by `main.py`, not systemd units.
- `audioop` (stdlib) is used for WAV resampling in `FileAudioSource`.
  It is deprecated in Python 3.11 (still present); v2 can switch to
  a maintained resampler.
- Single-room, single-turn. No conversation memory, no multi-room.

## 12. Reading guide (Python beginner)

Start here, in order:

1. `jarvis/ports.py` -- the contracts. Everything else makes sense
   once you know what each port promises.
2. `jarvis/runtime.py` -- the loop. This is the whole program's
   heartbeat in ~90 lines.
3. `jarvis/config.py` + `jarvis/errors.py` -- small, self-contained.
4. `jarvis/skills.py` + `jarvis/reflex.py` -- routing + skills.
5. `jarvis/audio.py` + `jarvis/wyoming_io.py` -- the adapters.
6. `jarvis/main.py` -- how it all gets built and started.
7. `tests/` -- each test file shows one module's behaviour with fakes.

Python features used (all standard, all worth learning): `@dataclass`
(config, Route, Turn), `typing.Protocol` (ports -- structural
typing, like Java interfaces but without inheritance), `Enum`
(state), `asyncio.run` (the contained async boundary), `subprocess`
(service management), `wave` + `audioop` (WAV handling).
