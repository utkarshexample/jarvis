# ADR-001: Body/brain separation via a protocol

- Status: Accepted
- Date: 2026-10-13

## Context

LLM vendors, models, and terms change fast. The physical body (Pi, mic,
speaker, camera, sensors) changes slowly. If the body is built around one
brain — one vendor's SDK, one API shape, one set of terms — every change of
brain is a rewrite, and a vendor's terms change can kill the product.

We also want the same body to work with a free-tier API, a local model, a
Strix Halo box, or a frontier cloud model, chosen per user and per request.

## Decision

The body exposes senses and actuators through a clean protocol. Brains are
pluggable clients of that protocol.

- The body sends the brain: transcribed text, sensor state, skill results,
  and (later) camera frames.
- The brain sends the body: text to speak, skill invocations, and actions.
- A reflex layer (Jev) sits between body and brain for fast, typed
  routing/gating decisions.
- No component of the body depends on one LLM vendor.

## Consequences

Positive:

- Swapping brains is a config change, not a rebuild.
- The body can be tested without a brain (scripted inputs).
- Local and cloud tiers coexist: local handles simple work, cloud handles
  hard reasoning, and the device degrades gracefully offline.
- Vendor terms changes (e.g. a non-commercial SDK clause) cannot kill the
  product, because no core component depends on any one vendor.

Negative:

- Protocol design is upfront work before any feature ships.
- Every request pays a network hop when the brain is remote (latency).
- The protocol must be versioned as the body gains senses (camera, new
  sensors) without breaking existing brains.

## Alternatives rejected

- **Single monolithic app** (body + one brain in one codebase): fastest to
  start, but couples the body to one brain forever. Rejected.
- **Cloud-only**: simplest, but the device goes dumb without internet and
  nothing is private by design. Rejected.
- **Vendor skill model** (Alexa skills / one ecosystem): skills live in
  the vendor's store under the vendor's rules. Rejected — the whole point
  of `SKILL.md` is that capabilities are plain files the user owns.
