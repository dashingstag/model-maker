---
name: bug-triage
description: Triage a pipeline finding into reports/BUG_LEDGER.md — classify component vs composition, assign an owning gate, file the row
argument-hint: "<finding description or failing check>"
allowed-tools:
  - read
  - grep
  - glob
  - edit
triggers:
  - user
  - model
---

Convert a found defect into a durable check. The workflow's rule:
**if a bug is visible on the component alone, it dies on the component
track** — composition gates only own relational failures.

## Classify

Ask first: *can this be seen on the component in isolation?*

- **Yes → component class.** Owns the earliest stage that has the
  information: prompt hallucination → C1 curation; matte/fringe → C2
  metrics; washed-out color/joint clip/prop drift → C3 unit render.
- **No → composition class.** Overlap, occlusion, parallax visibility,
  lit coverage, multi-actor sync → A2 checks on shots.
- **Infra** — tool/environment failures (node arch mismatch, queue
  hangs, renderer ignores override): fix the tool, own the fix, no gate.

## File it — reports/BUG_LEDGER.md

Match the existing table format exactly:

```
| <next #> | <one-line bug> | <component|composition|infra> |
  <how found — gate/shot/eyeball + evidence> | <fix applied> |
  <owning gate — the check that now guards it> | <status> |
```

- Statuses in use: `OPEN`, `PARTIAL`, `FIXED`, `RESOLVED` (RESOLVED =
  the "bug" was a misclassified check, e.g. expected front-row
  occlusion). `FIXED (by process)` for classes guarded by an existing
  stage rather than a metric.
- The owning gate must name a runnable check or an explicit waiver —
  "shot review" alone is not a gate; the vision checklist is the
  executor for eyeball-found classes.
- After the table, append proven metrics to "Check-accumulation
  additions" and follow-ups to "Open items for next run".

## Checks born from bugs — mechanics

- **Born advisory:** a new metric ships with `"gate_mode": "advisory"`
  and is promoted to `enforced` only after a healthy range is measured
  on ≥1 real run (lit_coverage read 0.04 on fine-looking art).
- **Must prove it measured something:** a reading of exactly 0,
  identical artifacts, or an empty set triggers a sanity flag on the
  *check*, not a pass on the art.
- Pick the **earliest** stage that can see it — a C2-fringe-class bug
  gated at A3 means the halo traveled two stages too far.
