"""Typed errors -- one per failure mode.

The runtime catches JarvisError (and only JarvisError) per loop
iteration, logs it, and keeps running. Anything else is a bug and
propagates loudly instead of being swallowed. See runtime.run_forever.
"""


class JarvisError(Exception):
    """Base class for every expected, handled failure."""


class ServiceUnavailable(JarvisError):
    """An STT / TTS service is down or not answering."""


class AudioError(JarvisError):
    """Mic / speaker missing, or an audio file that cannot be read."""


class BrainUnavailable(JarvisError):
    """The brain (LLM) cannot be reached."""


class SkillError(JarvisError):
    """A skill failed to load or to execute."""
