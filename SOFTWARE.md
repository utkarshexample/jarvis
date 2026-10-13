# Software — everything to install

Grouped by architecture layer. Status: what the Pi has today vs. what the
pilot still needs.

## Base

| Software | Purpose | Status | Notes |
|---|---|---|---|
| Raspberry Pi OS (Debian 12) | OS | Installed | Bookworm, 64-bit |
| Tailscale | Remote access | Installed | Personal plan, free |
| Muse Gadgets SDK (`musegadget`) | Muse link | Installed | Paired; token in root-only service storage |
| git, curl, build-essential | Dev tools | Verify | |
| Python 3 + pip + venv | Runtime language | Verify | All Jarvis code is Python |
| systemd | Services | Installed | One service per component |

## Body — audio

| Software | Purpose | Status | Notes |
|---|---|---|---|
| PipeWire + WirePlumber | Audio plumbing | To install/verify | Pi OS default audio stack |
| pipewire-pulse | PulseAudio compat | To install/verify | Lets Pulse-era tools work |
| ALSA utils (`alsa-utils`) | Audio testing | To install | `arecord` / `aplay` |

## Body — voice (Wyoming stack)

The Wyoming protocol (JSON lines + PCM audio) connects these as separate
small services. Each one is swappable.

| Software | Purpose | Status | License | Notes |
|---|---|---|---|---|
| wyoming-faster-whisper | Speech-to-text | To install | MIT | Offline, runs on Pi CPU |
| wyoming-piper | Text-to-speech | To install | MIT | Offline neural voices; needs a voice model (e.g. `en_US-lessac-medium`) |
| wyoming-openwakeword | Wake word | Phase 2 | MIT | "Hey Jarvis" later; pilot uses push-to-talk |
| wyoming-satellite | Reference satellite | Optional | MIT | Wires mic/speaker/wake-word together; reference only |

## Body — vision

| Software | Purpose | Status | License | Notes |
|---|---|---|---|---|
| Python OpenCV (`opencv-python`) + numpy | Camera capture, CV | To install | Apache 2.0 | Webcam via V4L2 |
| v4l-utils (`v4l2-ctl`) | Camera tools | To install | GPL | Inspect/list camera devices |

## Reflex layer

| Software | Purpose | Status | Notes |
|---|---|---|---|
| Jev API client (our code) | Fast typed decisions | To write | Cloud API only — weights unpublished, cannot run locally. 70–500 ms, ~$0.042/M input tokens. API key via env var, never in repo. |

## Brain layer (pluggable — pick one or more)

| Software | Purpose | Status | Notes |
|---|---|---|---|
| Muse (via Gadgets SDK) | Brain | Installed | Personal pairing |
| OpenAI / Anthropic API clients | Brain | To write | Plain HTTP; API keys via env var |
| Ollama or llama.cpp | Local lite LLM | Optional / phase 2 | Local 7B–14B for chatter + offline fallback. AMD: llama.cpp Vulkan backend on Linux. |

## Hands (phase 2)

| Software | Purpose | Status | License | Notes |
|---|---|---|---|---|
| Home Assistant | Smart-home hub | Phase 2 | Apache 2.0 | Lights, vacuum (Roborock), etc. |
| Roborock via Home Assistant | Vacuum control | Phase 2 | — | Vacuum already has LiDAR; reuse its map |

## Our code (this repo)

| Component | Purpose | Status |
|---|---|---|
| Jarvis runtime (Python) | Pipeline orchestration, skill discovery, service wiring | To write |
| Skill loader | Discovers `skills/*/SKILL.md`, validates, registers | To write |
| Health monitor | Temp, disk, memory, service health; alerts only on trouble | To write (owed) |
| systemd service files | One service per component | To write |

## Licensing rules for this project

- Prefer MIT / Apache 2.0 components.
- GPL components are usable if our distributed code stays open (it will).
- Never build on an unlicensed repo — no license means no rights.
- Keep an attribution file for everything used. See `NOTICE` (to be added
  as dependencies land).
