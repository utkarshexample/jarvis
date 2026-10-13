"""Reflex routing tests: no services, no hardware, pure logic."""

from jarvis.reflex import RuleReflex
from jarvis.skills import SkillRegistry


def _reflex() -> RuleReflex:
    skills = SkillRegistry.from_directory("skills")
    assert len(skills) == 2, skills.warnings
    return RuleReflex(skills)


def test_time_goes_to_skill():
    route = _reflex().route("hey jarvis, what time is it")
    assert route.kind == "skill"
    assert route.skill == "time"


def test_echo_goes_to_skill():
    route = _reflex().route("echo hello there")
    assert route.kind == "skill"
    assert route.skill == "echo"


def test_open_question_goes_to_brain():
    route = _reflex().route("tell me about black holes")
    assert route.kind == "brain"
    assert route.skill is None


def test_routing_is_case_insensitive():
    route = _reflex().route("WHAT TIME IS IT")
    assert route.kind == "skill"
    assert route.skill == "time"
