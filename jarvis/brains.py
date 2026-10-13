"""Brains: Brain implementations.

The Brain port is `respond(text) -> str`. Swapping brains is config:
main.py picks which class to construct; the runtime never knows which
one it got.

v1 ships EchoBrain only. It proves the wiring (reflex -> brain -> TTS)
without depending on any cloud service or SDK.

MuseBrain (v2 milestone): the Muse Gadgets SDK path. `musegadget
send-user-msg` sends a message to Muse from the device, but it is
one-way -- the reply comes back through the gadget daemon (`musegadget
run`), which means MuseBrain needs a listener for daemon replies and a
way to correlate them with requests. That is a real piece of async
integration, deliberately deferred -- it does not belong in v1.
"""

from __future__ import annotations


class EchoBrain:
    """Test brain: repeats the utterance back. Proves the wiring."""

    def respond(self, text: str) -> str:
        return f"You said: {text}"
