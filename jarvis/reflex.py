"""Reflex: the routing policy.

Reflex answers one question per utterance: does this go to a skill
or to the brain? It is deliberately dumb in v1 -- substring match
against each skill's trigger phrase, in registry order. The routing
*policy* lives here and only here; the runtime just follows the
Route it gets back.

v2 will replace RuleReflex with a JevReflex (same Reflex port) that
asks the Jev decision model instead of substring-matching. Nothing
else in the codebase changes when that happens.
"""

from __future__ import annotations

from .ports import Route
from .skills import SkillRegistry


class RuleReflex:
    """Substring-match routing. Simple, predictable, testable."""

    def __init__(self, skills: SkillRegistry) -> None:
        self.skills = skills

    def route(self, text: str) -> Route:
        lowered = text.lower()
        skill = self.skills.find(lowered)
        if skill is not None:
            return Route(kind="skill", skill=skill.name)
        return Route(kind="brain")
