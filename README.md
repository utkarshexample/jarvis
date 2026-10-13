# Jarvis — a body for an LLM

Open, Pi-class hardware that gives any AI agent ears, mouth, eyes, and hands.
Agent-agnostic. Capabilities come from drop-in `SKILL.md` files.

## What it is

Most voice assistants are locked to one vendor, one cloud, one set of skills.
Jarvis is the opposite: a cheap body (Raspberry Pi class) that any brain can
drive — Muse, Claude, OpenAI, a local model — and whose capabilities are
defined by skill files any developer can write.

- **Body**: Raspberry Pi 4 + mic + speaker + webcam + sensors. Senses and
  actuators only. The body does not contain the brain.
- **Reflexes**: fast, typed decisions (routing, gating, confidence) — see
  [ARCHITECTURE.md](ARCHITECTURE.md).
- **Brain**: pluggable. Free-tier API by default; a local model, a Strix Halo
  box, or a frontier cloud model for heavy lifting.
- **Skills**: drop a `SKILL.md` file in `skills/` and the device integrates
  it. No SDK, no app review. See [SKILLS.md](SKILLS.md).

## Design principles

1. **Cheap body, pluggable brains.** Never ask anyone to buy a $2,000 box
   to start. Heavy compute is an optional module, not a requirement.
2. **Agent-agnostic.** The body talks to brains through a clean protocol.
   Swapping brains is a config change, not a rebuild.
3. **Local-first where possible.** Wake word, simple commands, and sensors
   run on the device. Cloud tiers are chosen, not forced. The device
   degrades gracefully offline.
4. **Open interfaces.** The body touches anything on the local network and
   filesystem. Closed ecosystems (Echo Show camera/mic) stay peripherals,
   never the core.
5. **Not an Alexa/Siri clone.** The value is in things the big assistants
   can't or won't do: local, private, personalized, tied to your stuff.

## Status

Pilot: one room, one working voice loop, on a Raspberry Pi 4.

- [x] Pi 4 set up, reachable over Tailscale + SSH
- [x] Muse Gadgets SDK installed and paired
- [ ] Voice loop: STT -> reflex -> brain -> TTS (in progress)
- [ ] First skills: see [SKILLS.md](SKILLS.md)
- [ ] Home Assistant integration (phase 2)

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, layers, failure modes
- [SOFTWARE.md](SOFTWARE.md) — everything to install, by layer
- [SKILLS.md](SKILLS.md) — the `SKILL.md` contract
- [docs/adr/](docs/adr/) — architecture decision records

## License

To be decided for our own code (MIT expected). Third-party components keep
their own licenses — see [SOFTWARE.md](SOFTWARE.md).
