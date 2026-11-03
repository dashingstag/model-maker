---
description: Keep .devin/skills and rules in sync when the pipeline workflow, brief schema, shared vocabularies, or tool interfaces change
trigger: model_decision
---

When a change makes a skill's guidance stale, update the skill in the same
change — stale skill content is a bug, not a doc nit.

**Triggers for review:** edits to WORKFLOW.md's brief schema or stage
gates; new/renamed/removed fields a brief can carry; new `shared/` vocab
kinds (`skeletons/`, `actions/`, …); changed tool interfaces
(`tools/scaffold.py`, `gen_component.py`, `extract.py`, `publish.py`,
`godot/scripts/runner.gd`, job-file shape);
moved/renamed pipeline directories.

**What to update:**

- `.devin/skills/<name>/SKILL.md` — the field cheat-sheet, checklist, and
  process steps must match the current schema and gates
- `.devin/rules/*.md` — retire rules whose trigger no longer applies
- If a skill teaches a pattern a gate now enforces automatically, trim the
  skill's reminder — don't document what the tool checks

**Scope:** project skills under `.devin/skills/` are committed; update
them like code. Don't edit global skills outside this repo.
