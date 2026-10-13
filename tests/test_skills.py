"""Skill loading + execution tests: SKILL.md parsing, handlers."""

from jarvis.skills import SkillRegistry


def test_loads_both_skills():
    registry = SkillRegistry.from_directory("skills")
    assert len(registry) == 2
    assert registry.warnings == []


def test_time_skill_returns_a_time():
    registry = SkillRegistry.from_directory("skills")
    reply = registry.execute("time", "what time is it")
    assert reply.startswith("It is ")
    assert reply.endswith(("AM.", "PM."))


def test_echo_skill_strips_trigger():
    registry = SkillRegistry.from_directory("skills")
    assert registry.execute("echo", "echo hello world") == "hello world"


def test_unknown_skill_raises():
    registry = SkillRegistry.from_directory("skills")
    import pytest

    with pytest.raises(Exception, match="unknown skill"):
        registry.execute("nope", "hello")


def test_missing_skills_dir_warns_but_does_not_crash():
    registry = SkillRegistry.from_directory("does-not-exist")
    assert len(registry) == 0
    assert len(registry.warnings) == 1
