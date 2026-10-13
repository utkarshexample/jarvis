# Architecture

## Context (C4 level 1)

```
         +--------+
         |  User  |  speaks, is seen, is heard
         +---+----+
             |
             v
  +-------------------------+
  |  Jarvis body (Pi)       |  mic, speaker, camera, sensors
  +---+----------+----------+
      |          |
      v          v
+-----------+  +-----------+  +------------------+
|  Reflexes |  |  Brains   |  |  Home / devices  |
|  (Jev)    |  |  (LLMs)   |  |  (HA, vacuum, …) |
+-----------+  +-----------+  +------------------+
```

The user talks to the body. The body routes through reflexes to a brain.
The brain acts through skills, which reach home devices.

## Containers (C4 level 2)

| Container | Runs where | Job |
|---|---|---|
| Body services | Pi | Audio capture/playback, camera, sensors |
| Jarvis runtime | Pi | Pipeline orchestration, skill discovery |
| Reflex (Jev) | Cloud API | Fast typed decisions: routing, gating, confidence |
| Brain | Cloud API / local | Reasoning, conversation, planning |
| Skills | Pi | Capabilities, one `SKILL.md` each |
| Home Assistant | Pi / LAN | Smart-home control (phase 2) |

## The pipeline

```
mic -> VAD -> STT -> REFLEX -> BRAIN -> TTS -> speaker
                     |              |
                     v              v
                  local tier      skills -> actions
```

1. **Ears**: mic -> audio capture -> speech-to-text (faster-whisper).
2. **Reflex**: Jev decides — command or question? Local or cloud?
   Confident enough to act, or ask first? Which skill owns this?
3. **Brain**: the plugged-in LLM reasons, converses, plans.
4. **Mouth**: text-to-speech (Piper) -> speaker.
5. **Eyes** (phase 2): camera -> scene understanding.
6. **Hands** (phase 2): skills -> Home Assistant -> devices.

## Three layers

- **Body** (Pi): senses + actuators. No reasoning lives here.
- **Reflexes** (Jev): fast, typed, high-volume decisions. Returns
  Choice / Score / Noul with probabilities + confidence. The code branches
  on them: act / ask / escalate.
- **Brain** (any LLM): slow, open-ended reasoning and conversation.

## Two tiers

- **Local tier**: wake word, simple commands, sensor reads. Runs on the
  device, works offline.
- **Cloud tier**: open conversation, hard reasoning, Jev decisions.
  Chosen per request, not forced.

When the cloud is unreachable, the local tier keeps working and the cloud
tier pauses. Graceful degradation is a requirement, not a nicety.

## Key design decisions

See [docs/adr/](docs/adr/) for the full records. Headlines:

- **Body/brain separation via a protocol.** The body exposes senses and
  actuators; brains are pluggable clients. (ADR-001)
- **Agent-agnostic.** No part of the body depends on one LLM vendor.
- **Skills via `SKILL.md`.** Capabilities are markdown files the runtime
  discovers and integrates. No SDK, no app store. (See SKILLS.md.)
- **Confidence-gated actions.** The reflex layer returns confidence; the
  runtime acts, asks, or escalates based on it. Destructive or
  irreversible actions always confirm first.

## Failure modes (the architect's checklist)

| Failure | Behaviour |
|---|---|
| No internet | Local tier works; cloud tier pauses with a spoken notice |
| Mic unplugged | Runtime reports missing input device; local commands disabled |
| Brain timeout | Retry once, then tell the user plainly; never hang silently |
| Low-confidence action | Ask for confirmation instead of acting |
| Skill crashes | Isolate: one skill failing never kills the pipeline; log + report |
| Skill lies about its inputs | Validate all skill inputs/outputs against its declared schema |
| TTS fails mid-sentence | Log, fall back to a short spoken error or silence — never loop |

## What this is not

- Not an Alexa/Siri clone. Generic features lose to the vendors.
- Not a single-vendor product. No part of the core depends on one
  company's API, SDK, or terms.
- Not a cloud-only device. The local tier is real and must keep working.
