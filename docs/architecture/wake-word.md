# Wake word: "Hey Jarvis" (openWakeWord)

Status: implemented Oct 14, 2026 (tests pass). Live-test pending.

## Why

The loop had no gate: it recorded a 5 s chunk, transcribed it, acted,
then immediately recorded the next chunk, forever. The mic was
effectively always listening -- background noise, conversations, TV
all got transcribed. The wake word gates the turn: nothing is
transcribed or acted on until "Hey Jarvis" is heard.

The mic is still always on (for wake-word detection), but the
detection is 100% local -- no audio leaves the Pi until the wake
word is heard. Only the *text* of the utterance goes to the brain.

## How it fits the state machine

```
IDLE -> WAKE -> LISTENING -> TRANSCRIBING -> ROUTING -> THINKING -> SPEAKING -> IDLE
```

- **WAKE** (only when a wake word detector is provided): stream 160 ms
  frames through openWakeWord until the wake word is heard.
- **LISTENING**: record from the SAME stream (no audio lost between
  wake word and utterance), with a 1 s pre-roll buffer (the last
  second before detection, prepended so "Hey Jarvis, what time is
  it?" keeps the whole command), until VAD detects silence.
  Replaces the fixed 5 s window. Capped at `listen_max_s` (30 s).
  If the wake word is heard but no speech follows, gives up after
  `listen_seconds` (5 s) and returns a silence turn.
- The transcript has a leading "hey jarvis" stripped before routing.

## Streaming

`AudioSource.stream()` yields 160 ms frames (2560 samples, 5120
bytes). One frame feeds both detectors: openWakeWord wants multiples
of 1280 samples (2560 = 2x), Silero VAD wants 512-sample chunks
(2560 = 5x). The device stream (PortAudio `InputStream`, 1280-sample
blocksize... actually 2560-sample blocksize) uses a bounded queue
(decouples the audio callback from the consumer; drops the oldest
frame if the consumer falls behind; no frame in 5 s = mic died,
fail loudly). The caller closes the stream (``stream.close()``)
when the turn ends. A file stream ends when the file is exhausted
(no wake word -> silence turn, no crash).

## Detectors

| Detector | Library | Notes |
|---|---|---|
| Wake word | openWakeWord 0.6.0, model `hey_jarvis` | Fully local, no API key. **ONNX** framework -- tflite-runtime fails on this Pi (SystemError in CreateWrapperFromFile when loading the model). Models downloaded once via `openwakeword.utils.download_models()`. |
| VAD | pysilero-vad 3.4.0 (Silero VAD v6, bundled ggml model) | Frame split into five 512-sample chunks; speech if any chunk >= threshold. |

## Config

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| Enabled | `JARVIS_WAKE_WORD_ENABLED` | `true` | `false` = always-listening (old behaviour, for debugging) |
| Model | `JARVIS_WAKE_WORD_MODEL` | `hey_jarvis` | openWakeWord model name |
| Threshold | `JARVIS_WAKE_WORD_THRESHOLD` | `0.5` | Detection score. Raise to ~0.7 in noisy rooms |
| VAD silence | `JARVIS_VAD_SILENCE_S` | `1.0` | Silence after speech that ends the utterance |
| Listen cap | `JARVIS_LISTEN_MAX_S` | `30` | Cap on one utterance |

## Failure cases

| Failure | Behaviour |
|---|---|
| Wake word model fails to load (missing / bad model) | Log warning + fall back to always-listening (with VAD). Jarvis still works, just ungated |
| VAD fails to load | Log warning + fall back to the fixed `listen_seconds` window |
| Mic stream stalls (no frame in 5 s) | `AudioError` (fail loudly); `run_forever` logs and retries |
| False positive (TV / noise triggers "Hey Jarvis") | A turn starts, transcribes noise, routes to brain/skill. Mitigated by threshold + openWakeWord built-in VAD gating |
| False negative (wake word missed) | User repeats it. Mitigated by threshold tuning |
| Stream ends without wake word (file mode) | Silence turn, no crash |

## Mic note

The JBL mic is 8 kHz (PortAudio upsamples to 16 kHz). The wake word
model was trained on full-bandwidth audio, so accuracy on upsampled
8 kHz may dip. The webcam mic is 48 kHz mono (downsampled to 16 kHz,
no information loss) -- a better wake-word source if the JBL proves
flaky. v1 uses the JBL (same mic for wake + utterance, consistent).

## Debug logging (`JARVIS_DEBUG=1`)

When debug is on, the runtime logs `[DEBUG]` lines for every state
transition, the wake word score + a 30 s WAKE heartbeat (elapsed +
max score so far, for threshold tuning), VAD events (speech started,
silence end with duration/frames, no-speech give-up, cap), and
per-stage timings (transcribe / think / TTS / play). Off by default
(the normal log shows only `heard:` / `turn failed`). A failed turn
also logs the state it was in (`turn failed (...) in state X`).

Example (debug on, one turn):

```
[DEBUG] state: WAKE
[DEBUG] WAKE: waiting for wake word (threshold=0.5)
[DEBUG] WAKE: wake word detected (score=0.87, threshold=0.5)
[DEBUG] state: LISTENING
[DEBUG] LISTENING: recording (VAD, preroll 6 frames)
[DEBUG] VAD: speech started
[DEBUG] VAD: silence 1.0s, utterance end (3.2s, 20 frames)
[DEBUG] LISTENING: captured 102400 bytes (3.2s)
[DEBUG] state: TRANSCRIBING
[DEBUG] TRANSCRIBING: 'what time is it?' in 1.2s
[DEBUG] state: ROUTING
[DEBUG] ROUTING: -> skill time
[DEBUG] state: THINKING
[DEBUG] THINKING: skill 'time' replied in 0.0s
[DEBUG] state: SPEAKING
[DEBUG] SPEAKING: TTS in 0.8s
[DEBUG] SPEAKING: played 1.1s audio (took 1.1s)
[DEBUG] state: IDLE
```

## Live test plan

1. On the Pi: `~/.venvs/jarvis-runtime/bin/python -u -m jarvis.main`
2. Say something WITHOUT "Hey Jarvis" (e.g. "What time is it?") --
   Jarvis must NOT respond.
3. Say "Hey Jarvis, what time is it?" -- Jarvis must respond.
4. Background noise / TV -- Jarvis must NOT respond.
5. Long utterance ("Hey Jarvis, tell me ... [a long sentence]") --
   must NOT be cut off at 5 s (VAD, not the fixed window).
6. Tune `JARVIS_WAKE_WORD_THRESHOLD` if false positives / misses.
