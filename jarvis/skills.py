"""Skills: SKILL.md loading + skill execution.

A skill is two things, kept separate on purpose:

1. The contract: a SKILL.md file (see SKILLS.md) whose YAML
   frontmatter declares name / description / when / inputs /
   outputs / permissions. ``when`` is the trigger phrase v1 matches
   on (substring, case-insensitive).
2. The handler: a Python function that takes the utterance and
   returns the reply text.

In v1 the handlers live in HANDLERS below, keyed by skill name.
In v2 they move into the skill's own folder (a ``handler.py`` per
skill), so a skill becomes fully drop-in. The registry and the
frontmatter format do not change when that happens.

A skill whose name has no handler is skipped with a warning -- a
missing handler must never take down the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from .errors import SkillError

Handler = Callable[[str], str]


def _time_handler(text: str) -> str:
    return f"It is {datetime.now().strftime('%-I:%M %p')}."


def _echo_handler(text: str) -> str:
    stripped = text.replace("echo", "", 1).strip()
    return stripped if stripped else text


HANDLERS: dict[str, Handler] = {
    "time": _time_handler,
    "echo": _echo_handler,
}


@dataclass(frozen=True)
class LoadedSkill:
    """A skill: contract (from SKILL.md) + handler (Python function)."""

    name: str
    description: str
    trigger: str
    handler: Handler

    def execute(self, text: str) -> str:
        try:
            return self.handler(text)
        except Exception as exc:
            raise SkillError(f"skill {self.name!r} failed: {exc}") from exc


class SkillRegistry:
    """All loaded skills. Owns lookup (find) and execution."""

    def __init__(self, skills: list[LoadedSkill], warnings: list[str] | None = None) -> None:
        self._skills = skills
        self.warnings = warnings or []

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self):
        return iter(self._skills)

    @classmethod
    def from_directory(cls, path: str | Path) -> "SkillRegistry":
        """Load every <skill>/SKILL.md under ``path``."""
        skills: list[LoadedSkill] = []
        warnings: list[str] = []
        root = Path(path)
        if not root.exists():
            return cls([], [f"skills dir not found: {root}"])
        for skill_file in sorted(root.glob("*/SKILL.md")):
            try:
                skill = _load_skill_file(skill_file)
            except SkillError as exc:
                warnings.append(str(exc))
                continue
            skills.append(skill)
        return cls(skills, warnings)

    def find(self, lowered_text: str) -> LoadedSkill | None:
        """First skill whose trigger appears in the utterance, or None."""
        for skill in self._skills:
            if skill.trigger and skill.trigger.lower() in lowered_text:
                return skill
        return None

    def execute(self, name: str, text: str) -> str:
        for skill in self._skills:
            if skill.name == name:
                return skill.execute(text)
        raise SkillError(f"unknown skill: {name!r}")


def _load_skill_file(path: Path) -> LoadedSkill:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SkillError(f"{path}: missing YAML frontmatter")
    _, frontmatter, _ = text.split("---", 2)
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{path}: bad YAML frontmatter: {exc}") from exc
    name = str(data.get("name", "")).strip()
    if not name:
        raise SkillError(f"{path}: SKILL.md has no name")
    if name not in HANDLERS:
        raise SkillError(f"{path}: skill {name!r} has no handler (skipped)")
    return LoadedSkill(
        name=name,
        description=str(data.get("description", "")),
        trigger=str(data.get("when", "")),
        handler=HANDLERS[name],
    )
