---
description: Check mechanics when adding or modifying pipeline gates, metrics, or Godot capture code — advisory-first, evidence emission, deterministic capture
trigger: model_decision
---

**New checks are born advisory.** Ship with `"gate_mode": "advisory"` in
the manifest; promote to `enforced` only after the healthy range is
measured on ≥1 real run. A miscalibrated gate is noise
(`captain_lit_coverage` read 0.04 on art that looked fine).

**A check must prove it measured something.** Degenerate results —
metric exactly 0, identical artifacts, empty sets, unchanged values —
trigger a sanity flag on the check, not a pass on the art. Every gate
emits *evidence* (numbers, hashes, file existence), never just
pass/fail.

**Vision verdicts are persisted.** Any eyeball/agent/human judgment
writes `vision.json` — verdict, checklist, named actor, timestamp, flags
— or it didn't happen. Waivers are explicit fields, not omissions.

**Deterministic capture only** (godot/scripts/runner.gd): drive animation
with `AnimationPlayer.seek(t)` per pose/event + `set_process(false)`
before capture — never accumulate `_process` delta or wall-clock.
Multi-actor shots use one shared clock with `sync_on` resolved through
clip `events`.

**Earliest-stage ownership:** a bug visible on a component alone dies on
its track (file via /bug-triage); composition gates stay small by design.
