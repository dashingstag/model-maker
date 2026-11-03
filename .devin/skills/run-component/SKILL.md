---
name: run-component
description: Drive one component through the C-track — generate → curate → extract → unit render → certify — with gate evidence and failure routing
argument-hint: "<component_id> [--goal <goal>] [--seeds N]"
allowed-tools:
  - read
  - grep
  - glob
  - edit
  - exec
triggers:
  - user
  - model
---

Take one `pipeline/components/<id>/` through the component track to
`certified`. Manifest status progression: `wip → generating → curated →
processed → certified`; `stale`/`needs_human` are the failure exits.
WORKFLOW.md sections C1–C3 + "Vision, human gates, and waivers" are the
contract — read them when behavior matters.

## Stage commands

```bash
# C1 generate — ComfyUI must be up (curl http://127.0.0.1:8188/system_stats)
python tools/gen_component.py <id> [--seeds N] [--goal <goal>] [--wait 60]

# curate — human contact-sheet pick or agent checklist; winner(s) copied
# to accepted/ (sprite: one per pose, named <pose>.png; ui/parallax:
# src.png) + sidecar gen.json; rejected seeds stay logged in
# candidates/index.json

# C2 extract — uses the rembg venv python, NOT system python
<comfyui_python from tools/env.json> tools/extract.py <id> [--goal <goal>] [--wait 60]

# C3 unit render — publish then run the harness (windowed, unminimized —
# gl_compatibility cannot render headless on Windows)
python tools/publish.py <goal> --wait 60
<godot exe from tools/env.json> --path godot -- <abs path to jobs.json>
```

## Per-type notes

- `sprite_variant` — **transform-only**: skip C1 entirely (gen prints a
  notice and exits); go straight to extract after the `of` base is
  `processed`. Locks its base automatically.
- `sprite` — C1 locks `captain_3d` too (depth source); poses from
  `brief.json` drive Blender `_render/` depth + `_n` normals.
- `ui_image`/`parallax` — plain txt2img; accepted file must be `src.png`.
- `glb` — C1 is `blender_pirate.py` → `build/` + `export/`; extract
  validates tris vs `tri_budget` and lists animations.

## Gates (don't skip — evidence, not vibes)

- C1 out: `candidates/` populated; `index.json` has every seed's
  provenance. Degenerate/hallucinated candidates stay logged, not
  deleted.
- C2 out: `manifest.json` written atomically with per-type gate fields —
  sprite `fringe_px`/`gate.fringe_ok`, glb `tris`/`gate.tris_ok`,
  variant `variants` + `of`. Check `gate.*` values, not just existence.
- C3 out: `unit_render/` shots + `vision.json` (checklist verdicts, actor,
  ts, flags). **Every file under `accepted/` must pass vision** — a blind
  accept once shipped an unverified walk_b.
- Certify: set `manifest.status: "certified"` (atomic write via
  `tools/pipelib.py:atomic_json`) only after vision passes.

## Failure routing

- A failed check loops to the **earliest broken stage** — don't re-run
  publish for a bad matte; re-run extract.
- Locks: `--wait N` polls; a `LockHeld` exit means another run owns the
  component — report the owner, don't force.
- After 2 failed regen rounds → `manifest.status: "needs_human"` with the
  blocking reason in `waiver`/`history`, and say so plainly.
- Never `rmtree` a stage folder to retry — write-once per rev; the
  validator archives to `history/rev<n>/`.
