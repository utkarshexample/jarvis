# Skills — the `SKILL.md` contract

Skills are how Jarvis gains capabilities. A skill is a directory in
`skills/` containing a `SKILL.md` file and optional scripts. The runtime
discovers skill files, validates them, and exposes them to the brain.
No SDK. No app review. Drop the file in, the device integrates it.

## Directory layout

```
skills/
  morning-briefing/
    SKILL.md
    briefing.py        # optional: the code the skill runs
  den-light/
    SKILL.md
```

## `SKILL.md` format

Frontmatter (machine-read) + body (human/agent-read):

```markdown
---
name: morning-briefing
description: Spoken morning briefing: weather, transit, calendar.
when: User asks for the morning briefing, what's today, or what's on.
inputs:
  - name: location
    type: string
    required: false
    description: City for weather. Defaults to Kitchener.
outputs:
  - name: briefing_text
    type: string
    description: Plain text to speak aloud.
permissions:
  network: true        # may call weather/calendar APIs
  filesystem: none
  devices: none
---

# Morning briefing

How to run: `python3 briefing.py [--location CITY]`
Output: JSON `{"briefing_text": "..."}` on stdout.
Failure: non-zero exit + `{"error": "..."}` on stderr.
...
```

Required frontmatter fields: `name`, `description`, `when`, `inputs`,
`outputs`, `permissions`.

## Discovery and integration

1. On start (and on file change), the runtime scans `skills/*/SKILL.md`.
2. Each file is parsed and validated: required fields present, `name`
   unique, `inputs`/`outputs` well-formed.
3. Valid skills are registered. The brain sees: name, description, when
   to use it, and its input/output schema — nothing else.
4. When the brain invokes a skill, the runtime runs its command with the
   declared inputs, validates the output against the declared schema, and
   returns it. Invalid output is a skill failure, never a crash.

## Safety rules

- **No secrets in `SKILL.md`.** API keys come from environment variables.
- **Declare permissions.** `network`, `filesystem`, `devices` must be
  honest. The runtime enforces them; a skill that exceeds its declared
  permissions is rejected.
- **Destructive actions confirm.** A skill that changes state
  irreversibly (buy, delete, send, unlock) must be marked
  `confirm: true`. The runtime asks the user before running it.
- **Fail structured.** Every skill returns JSON on stdout or a JSON error
  on stderr with a non-zero exit. No stack traces to the user.
- **Idempotent where possible.** Running a skill twice should not double
  the effect (e.g. check state before acting).

## Example skill: morning briefing

`skills/morning-briefing/SKILL.md` — weather + transit + calendar, spoken
aloud while the user gets ready. See the format above; this is skill #1.

## Writing a skill (for developers)

1. Copy an existing skill directory.
2. Write the `SKILL.md` first — the contract before the code.
3. Implement the script. Keep it small and single-purpose.
4. Test it standalone: `python3 your-skill.py` must print valid JSON.
5. Drop it in `skills/`. The runtime picks it up with no restart ceremony.

The contract is the product: if the `SKILL.md` is right, the integration
is automatic. If it is wrong, the skill is rejected with a reason.
