"""Jarvis: a body for an LLM.

The runtime is organised as Ports & Adapters (see
docs/architecture/code-pattern.md):

- ``ports``    -- the contracts (interfaces) every part speaks.
- ``runtime``  -- the conductor: one state machine, no hardware knowledge.
- ``audio``    -- AudioSource / AudioSink implementations (device + file).
- ``wyoming_io`` -- STT / TTS adapters speaking the Wyoming protocol.
- ``reflex``   -- routing policy: skill vs brain.
- ``brains``   -- Brain implementations (echo for v1, Muse in v2).
- ``skills``   -- SKILL.md loading + skill handlers.
- ``config``   -- configuration, from env vars with sane defaults.
- ``errors``   -- typed errors, one per failure mode.
- ``main``     -- composition root: builds everything, starts services.
"""

__version__ = "0.1.0"
